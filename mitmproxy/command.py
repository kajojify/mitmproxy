"""
    This module manages and invokes typed commands.
"""
import asyncio
import inspect
import types
import typing
import textwrap
import functools
import sys

import mitmproxy.types
from mitmproxy import exceptions
from mitmproxy import language as lang


def verify_arg_signature(f: typing.Callable, args: list, kwargs: dict) -> None:
    sig = inspect.signature(f)
    try:
        sig.bind(*args, **kwargs)
    except TypeError as v:
        raise exceptions.CommandError("command argument mismatch: %s" % v.args[0])


def typename(t: type) -> str:
    """
        Translates a type to an explanatory string.
    """
    if t == inspect._empty:  # type: ignore
        raise exceptions.CommandError("missing type annotation")
    to = mitmproxy.types.CommandTypes.get(t, None)
    if not to:
        raise exceptions.CommandError("unsupported type: %s" % getattr(t, "__name__", t))
    return to.display


RunningCommand = typing.NamedTuple(
    "RunningCommand",
    [
        ("cmdstr", str),
        ("task", asyncio.Future)
    ],
)


class AsyncExecutionManager:
    def __init__(self) -> None:
        self.counter: int = 0
        self.running_cmds: typing.Dict[int, RunningCommand] = {}

    def add_command(self, cmd: RunningCommand) -> None:
        self.counter += 1
        cmd.task.add_done_callback(functools.partial(self._delete_callback,
                                                     cid=self.counter))
        self.running_cmds[self.counter] = cmd

    def stop_command(self, cid: int) -> None:
        try:
            cmd = self.running_cmds[cid]
        except KeyError:
            raise ValueError(f"There is not the command with id={cid}")
        else:
            cmd.task.cancel()
            del self.running_cmds[cid]

    def get_running(self) -> typing.List[typing.Tuple[int, str]]:
        running = []
        for cid in sorted(self.running_cmds):
            running.append((cid, self.running_cmds[cid].cmdstr))
        return running

    def _delete_callback(self, task: asyncio.Task, cid: int) -> None:
        del self.running_cmds[cid]


class Command:
    def __init__(self, manager, path, func) -> None:
        self.path = path
        self.manager = manager
        self.func = func
        self.asyncf = True if asyncio.iscoroutinefunction(func) else False
        sig = inspect.signature(self.func)
        self.help = None
        if func.__doc__:
            txt = func.__doc__.strip()
            self.help = "\n".join(textwrap.wrap(txt))

        self.has_positional = False
        for i in sig.parameters.values():
            # This is the kind for *args parameters
            if i.kind == i.VAR_POSITIONAL:
                self.has_positional = True
        self.paramtypes = [v.annotation for v in sig.parameters.values()]
        if sig.return_annotation == inspect._empty:  # type: ignore
            self.returntype = None
        else:
            self.returntype = sig.return_annotation
        # This fails with a CommandException if types are invalid
        self.signature_help()

    def paramnames(self) -> typing.Sequence[str]:
        v = [typename(i) for i in self.paramtypes]
        if self.has_positional:
            v[-1] = "*" + v[-1]
        return v

    def retname(self) -> str:
        return typename(self.returntype) if self.returntype else ""

    def signature_help(self) -> str:
        params = " ".join(self.paramnames())
        ret = self.retname()
        if ret:
            ret = " -> " + ret
        return "%s %s%s" % (self.path, params, ret)

    def prepare_args(self, args: typing.Sequence[typing.Any]) -> typing.List[typing.Any]:
        verify_arg_signature(self.func, list(args), {})

        remainder: typing.Sequence[str] = []
        if self.has_positional:
            remainder = args[len(self.paramtypes) - 1:]
            args = args[:len(self.paramtypes) - 1]

        pargs = []

        for arg, paramtype in zip(args, self.paramtypes):
            if not isinstance(arg, str):
                t = mitmproxy.types.CommandTypes.get(paramtype, None)
                if t.is_valid(self.manager, t, arg):
                    pargs.append(arg)
                else:
                    raise exceptions.CommandError(
                        f"{arg} is unexpected data for {t.display} type"
                    )
            else:
                pargs.append(parsearg(self.manager, arg, paramtype))
        pargs.extend(remainder)
        return pargs

    def call(self, args: typing.Sequence[typing.Any]) -> typing.Any:
        """
            Call the command with a list of arguments.
        """
        ret = self.func(*self.prepare_args(args))

        if ret is None and self.returntype is None:
            return
        typ = mitmproxy.types.CommandTypes.get(self.returntype)
        if not typ.is_valid(self.manager, typ, ret):
            raise exceptions.CommandError(
                f"{self.path} returned unexpected data - expected {typ.display}"
            )
        return ret

    async def async_call(self, args: typing.Sequence[typing.Any]) -> typing.Any:
        """
            Call the command with a list of arguments asynchronously.
        """
        ret = await self.func(*self.prepare_args(args))

        if ret is None and self.returntype is None:
            return
        typ = mitmproxy.types.CommandTypes.get(self.returntype)
        if not typ.is_valid(self.manager, typ, ret):
            raise exceptions.CommandError(
                f"{self.path} returned unexpected data - expected {typ.display}"
            )
        return ret


ParseResult = typing.NamedTuple(
    "ParseResult",
    [
        ("value", str),
        ("type", typing.Type),
        ("valid", bool),
    ],
)


class CommandManager(mitmproxy.types._CommandBase):
    def __init__(self, master):
        self.master = master
        self.async_manager = AsyncExecutionManager()
        self.command_parser = lang.parser.create_parser(self)
        self.partial_parser = lang.partial_parser.create_parser(self)
        self.commands: typing.Dict[str, Command] = {}
        self.oneword_commands: typing.List[str] = []

    def collect_commands(self, addon):
        for i in dir(addon):
            if not i.startswith("__"):
                o = getattr(addon, i)
                try:
                    is_command = hasattr(o, "command_path")
                except Exception:
                    pass  # hasattr may raise if o implements __getattr__.
                else:
                    if is_command:
                        try:
                            self.add(o.command_path, o)
                        except exceptions.CommandError as e:
                            self.master.log.warn(
                                "Could not load command %s: %s" % (o.command_path, e)
                            )

    def add(self, path: str, func: typing.Callable):
        self.commands[path] = Command(self, path, func)
        # Collecting one-word command names for lexer
        if len(path.split(".")) == 1:
            self.oneword_commands.append(path)

    def parse_partial(
        self,
        cmdstr: str
    ) -> typing.Tuple[typing.Sequence[ParseResult], typing.Sequence[str]]:
        """
            Parse a possibly partial command. Return markup
            language structures and whitespaces map
        """
        lex = lang.lexer.InteractiveLexer(cmdstr, self.oneword_commands)

        try:
            typer = self.partial_parser.parse(lex)
        except exceptions.CommandError:
            typer = [("commander_invalid", cmdstr)]
            lex.whitespace_map = []
        return typer, lex.whitespace_map

    def get_command_by_path(self, path: str) -> Command:
        """
            Returns command by its path. May raise CommandError.
        """
        if path not in self.commands:
            raise exceptions.CommandError(f"Unknown command: {path}")
        return self.commands[path]

    def call(self, path: str, *args: typing.Sequence[typing.Any]) -> typing.Any:
        """
            Call a command with native arguments. May raise CommandError.
        """
        return self.get_command_by_path(path).func(*args)

    def call_strings(self, path: str, args: typing.Sequence[str]) -> typing.Any:
        """
            Call a command using a list of string arguments. May raise CommandError.
        """
        return self.get_command_by_path(path).call(args)

    def async_execute(self, cmdstr: str) -> asyncio.Future:
        """
            Schedule a command to be executed. May raise CommandError.
        """
        lex = lang.lexer.create_lexer(cmdstr, self.oneword_commands)
        parsed_cmd = self.command_parser.parse(lexer=lex, async_exec=True)

        execution_coro = lang.traversal.execute_parsed_line(parsed_cmd)
        command_task = asyncio.ensure_future(execution_coro)
        self.async_manager.add_command(RunningCommand(cmdstr, command_task))
        return command_task

    def execute(self, cmdstr: str) -> typing.Any:
        """
            Execute a command string. May raise CommandError.
        """
        lex = lang.lexer.create_lexer(cmdstr, self.oneword_commands)
        parsed_cmd = self.command_parser.parse(lexer=lex)
        return parsed_cmd

    def dump(self, out=sys.stdout) -> None:
        cmds = list(self.commands.values())
        cmds.sort(key=lambda x: x.signature_help())
        for c in cmds:
            for hl in (c.help or "").splitlines():
                print("# " + hl, file=out)
            print(c.signature_help(), file=out)
            print(file=out)


def parsearg(manager: CommandManager, spec: str, argtype: type) -> typing.Any:
    """
        Convert a string to a argument to the appropriate type.
    """
    t = mitmproxy.types.CommandTypes.get(argtype, None)
    if not t:
        raise exceptions.CommandError(f"Unsupported argument type: {argtype}")
    try:
        return t.parse(manager, argtype, spec)  # type: ignore
    except exceptions.TypeError as e:
        raise exceptions.CommandError from e


def command(path):
    def decorator(function):
        if asyncio.iscoroutinefunction(function):
            @functools.wraps(function)
            async def wrapper(*args, **kwargs):
                verify_arg_signature(function, args, kwargs)
                return await function(*args, **kwargs)
        else:
            @functools.wraps(function)
            def wrapper(*args, **kwargs):
                verify_arg_signature(function, args, kwargs)
                return function(*args, **kwargs)
        wrapper.__dict__["command_path"] = path
        return wrapper
    return decorator


def argument(name, type):
    """
        Set the type of a command argument at runtime. This is useful for more
        specific types such as mitmproxy.types.Choice, which we cannot annotate
        directly as mypy does not like that.
    """
    def decorator(f: types.FunctionType) -> types.FunctionType:
        assert name in f.__annotations__
        f.__annotations__[name] = type
        return f
    return decorator
