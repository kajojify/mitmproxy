import abc
import typing

import urwid
from urwid.text_layout import calc_coords

import mitmproxy.flow
import mitmproxy.master
import mitmproxy.command
import mitmproxy.types


class Completer:  # pragma: no cover
    @abc.abstractmethod
    def cycle(self) -> str:
        pass


class ListCompleter(Completer):
    def __init__(
        self,
        start: str,
        options: typing.Sequence[str]
    ) -> None:
        self.start = start
        self.options: typing.Sequence[str] = []
        for o in options:
            if o.startswith(start):
                self.options.append(o)
        self.options.sort()
        self.offset = 0

    def cycle(self) -> str:
        if not self.options:
            return self.start
        ret = self.options[self.offset]
        self.offset = (self.offset + 1) % len(self.options)
        return ret


CompletionState = typing.NamedTuple(
    "CompletionState",
    [
        ("completer", Completer),
        ("parse", typing.Sequence[mitmproxy.command.ParseResult])
    ]
)


class CommandBuffer:
    def __init__(self, master: mitmproxy.master.Master, start: str = "") -> None:
        self.master = master
        self.text = start
        # Cursor is always within the range [0:len(buffer)].
        self.autoclosing = True
        self._cursor = len(self.text)
        self.completion: CompletionState = None

    @property
    def cursor(self) -> int:
        return self._cursor

    @cursor.setter
    def cursor(self, x) -> None:
        if x < 0:
            self._cursor = 0
        elif x > len(self.text):
            self._cursor = len(self.text)
        else:
            self._cursor = x

    def render(self):
        """
            This function is somewhat tricky - in order to make the cursor
            position valid, we have to make sure there is a
            character-for-character offset match in the rendered output, up
            to the cursor. Beyond that, we can add stuff.
        """
        typer, wm = self.master.commands.parse_partial(self.text)
        print("WS MAP: ", wm)
        if not isinstance(typer, list):
            markup = typer.generate_markup()
        else:
            markup = typer
        if not markup:
            markup = [("text", "")]
        typer = markup[::-1]
        print("markup: ", markup)
        reunited_typer = []
        for m in wm:
            if m is None and typer:
                attr, elem = typer.pop()
                reunited_typer.append((attr, elem))
            else:
                reunited_typer.append(("text", m))
        reunited = reunited_typer + typer[::-1]
        print("Reunited typer: ", reunited)
        return [("text", self.text)]

    def left(self) -> None:
        self.cursor = self.cursor - 1

    def right(self) -> None:
        self.cursor = self.cursor + 1

    def cycle_completion(self) -> None:
        if not self.completion:
            parts, remainhelp = self.master.commands.parse_partial(self.text[:self.cursor])
            last = parts[-1]
            ct = mitmproxy.types.CommandTypes.get(last.type, None)
            if ct:
                self.completion = CompletionState(
                    completer = ListCompleter(
                        parts[-1].value,
                        ct.completion(self.master.commands, last.type, parts[-1].value)
                    ),
                    parse = parts,
                )
        if self.completion:
            nxt = self.completion.completer.cycle()
            buf = "".join([i.value for i in self.completion.parse[:-1]]) + nxt
            self.text = buf
            self.cursor = len(self.text)

    def backspace(self) -> None:
        if self.cursor == 0:
            return
        brackets = ("''", '""', "()", "[]")
        possible_brackets_pair = self.text[self.cursor - 1:self.cursor + 1]
        if possible_brackets_pair in brackets:
            self.text = self.text[:self.cursor - 1] + self.text[self.cursor + 1:]
        elif self.text[self.cursor - 1] == "]":
            self.autoclosing = False
            self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
        elif self.text[self.cursor - 1] == "[":
            self.autoclosing = True
            self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
        else:
            self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
        self.cursor = self.cursor - 1
        self.completion = None

    def insert(self, k: str) -> None:
        """
            Inserts text at the cursor.
        """
        if k == "[":
            self.autoclosing = True
        self.text = self.text[:self.cursor] + k + self.text[self.cursor:]
        self.cursor += 1
        self.completion = None


class CommandEdit(urwid.WidgetWrap):
    leader = ": "

    def __init__(self, master: mitmproxy.master.Master, text: str) -> None:
        super().__init__(urwid.Text(self.leader))
        self.master = master
        self.cbuf = CommandBuffer(master, text)
        self.update()

    def keypress(self, size, key):
        if key == "backspace":
            self.cbuf.backspace()
        elif key == "left":
            self.cbuf.left()
        elif key == "right":
            self.cbuf.right()
        elif key == "tab":
            self.cbuf.cycle_completion()
        elif len(key) == 1:
            self.cbuf.insert(key)
        self.update()

    def update(self):
        self._w.set_text([self.leader, self.cbuf.render()])

    def render(self, size, focus=False):
        (maxcol,) = size
        canv = self._w.render((maxcol,))
        canv = urwid.CompositeCanvas(canv)
        canv.cursor = self.get_cursor_coords((maxcol,))
        return canv

    def get_cursor_coords(self, size):
        p = self.cbuf.cursor + len(self.leader)
        trans = self._w.get_line_translation(size[0])
        x, y = calc_coords(self._w.get_text()[0], trans, p)
        return x, y

    def get_edit_text(self):
        return self.cbuf.text
