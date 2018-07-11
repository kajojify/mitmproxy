import typing

import mitmproxy.types
from mitmproxy import exceptions


class CommandLine:
    def __init__(self, line):
        self.line = line

    def generate_markup(self):
        markup = []
        print("Line: ", self.line)
        for element in self.line:
            if element:
                if isinstance(element, Array) or isinstance(element, CommandSpace):
                    markup.extend(self._collect_markups(element))
                else:
                    markup.append(("text", element))
        return markup

    def _collect_markups(self, space):
        if isinstance(space, CommandSpace):
            markup = [(space.markup_attr, space.name)]
            remhelp = space.get_remhelp()
        else:
            markup, remhelp = [], []
        arguments = space.head + space.arguments
        print("Args: ", space.arguments)
        print("Rem: ", remhelp)
        for arg in arguments:
            if arg is not None:
                if isinstance(arg, Array) or isinstance(arg, CommandSpace):
                    markup.extend(self._collect_markups(arg))
                elif isinstance(arg, Arg):
                    display_attr = ("commander_invalid", "text")[arg.valid]
                    markup.append((display_attr, arg.value))
                else:
                    if isinstance(arg, tuple):
                        markup.append(("m_text", arg[0]))
                    else:
                        markup.append(("text", arg))
        if remhelp:
            markup += [("m_text", " ")]
        markup += remhelp
        markup += space.tail
        return markup

    def get_last(self):
        pass


class CommandSpace:
    def __init__(self, command_name, manager, head=None,
                 arguments=None, tail=None, autoclosing=False):
        self.name = command_name
        self.manager = manager
        self.head = [h for h in head if h] if head else []
        self.params = []
        self.type = mitmproxy.types.Cmd
        validC = self.is_valid(self.type, self.name)
        if validC:
            self.params.extend(manager.commands[self.name].paramtypes)
        self.arguments = []

        if arguments:
            for arg in arguments:
                try:
                    typ = self.params.pop(0)
                except IndexError:
                    self.arguments.append(Arg(arg, None, False))
                valid = self.is_valid(typ, arg)
                self.arguments.append(Arg(arg, typ, valid))

        self.tail = [t for t in tail if t] if tail else []
        if autoclosing:
            self.tail.append((")",))

        markup_attrs = ("commander_invalid", "commander_command")
        self.markup_attr = markup_attrs[validC]


    def get_remhelp(self):
        remhelp: typing.List[str] = []
        for x in self.params:
            remt = mitmproxy.types.CommandTypes.get(x, None)
            remhelp.append(("commander_hint", " %s" % remt.display))
        return remhelp

    def is_valid(self, typ, value):
        to = mitmproxy.types.CommandTypes.get(typ, None)
        valid = False
        if to:
            try:
                to.parse(self.manager, typ, value)
            except exceptions.TypeError:
                valid = False
            else:
                valid = True
        return valid


class Array:
    def __init__(self, space, autoclosing=False):
        self.arguments = space
        self.head = []
        self.tail = []
        if autoclosing and self.arguments:
            self.arguments.append(("]",))

class Arg:
    def __init__(self, value, type, valid):
        self.value = value
        self.type = type
        self.valid = valid
