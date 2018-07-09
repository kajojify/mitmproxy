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
                    markup.extend(self.collect_markups(element))
                else:
                    markup.append(("text", element))
        return markup

    def collect_markups(self, space):
        if isinstance(space, CommandSpace):
            markup = [(space.markup_attr, space.name)]
            remhelp = space.get_remhelp()
        else:
            markup, remhelp = [], []
        arguments = space.arguments
        for arg in arguments:
            if arg:
                if isinstance(arg, Array) or isinstance(arg, CommandSpace):
                    markup.extend(self.collect_markups(arg))
                else:
                    markup += [arg]
        markup += remhelp
        return markup


class CommandSpace:
    def __init__(self, command_name, arguments, manager):
        self.name = command_name
        self.manager = manager
        self.arguments = arguments
        markup_attrs = ("commander_invalid", "commander_command")
        valid = self.is_valid(mitmproxy.types.Cmd, self.name)
        self.markup_attr = markup_attrs[valid]
        self.params = []
        if valid:
            self.params.extend(manager.commands[self.name].paramtypes)

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
        if autoclosing and self.arguments:
            self.arguments.append("]")
