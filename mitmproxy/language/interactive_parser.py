import typing

import ply.lex as lex
import ply.yacc as yacc

from mitmproxy import exceptions
from mitmproxy.language.lexer import CommandLanguageLexer
import mitmproxy.types


class CommandLine:
    def __init__(self, line):
        self.line = line

    def generate_markup(self):
        markup = []
        for element in self.line:
            if element is not None:
                if isinstance(element, CommandSpace):
                    markup.extend(self.collect_markups(element))
                else:
                    markup += [element]

    def collect_markups(self, command_space):
        markup = [(command_space.markup_attr, command_space.name)]
        arguments = command_space.arguments
        remhelp = command_space.get_remhelp()
        for arg in arguments:
            if isinstance(arg, CommandSpace, Array):
                markup.extend(self.collect_markups(arg))
            else:
                markup += [arg]


class CommandSpace:
    def __init__(self, command_name, arguments):
        self.name = command_name
        self.arguments = arguments
        self.markup_attrs = ("commander_invalid", "commander_command")

    def add_command_space(self, command_space):
        _, arglist = command_space


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
    def __init__(self, arguments=None, autoclosing=False):
        self.arguments = arguments


class InteractivePartialParser:
    # the list of possible tokens is always required
    tokens = CommandLanguageLexer.tokens

    def __init__(self, commands):
        self.commands = commands
        self.parsed_line = None

    def p_command_call(self, p):
        """command_line : empty
                        | eorws command_line_structure eorws"""
        self.parsed_line = CommandLine(p[1:])

    def p_possible_start(self, p):
        """command_line_structure : empty
                                  | array
                                  | command_call_no_parentheses
                                  | command_call_with_parentheses"""
        p[0] = p[1]

    def p_command_call_no_parentheses(self, p):
        """command_call_no_parentheses : command_name eorws argument_list"""
        cs = CommandSpace(p[0])
        cs.add_command_space(p[2:])

    def p_argument_list(self, p):
        """argument_list : empty
                         | argument
                         | argument_list eorws argument"""
        if len(p) == 2:
            p[0] = [] if p[1] is None else [p[1]]
        else:
            p[0] = p[1]
            p[0].append(p[1:])

    def p_argument(self, p):
        """argument : PLAIN_STR
                    | QUOTED_STR
                    | COMMAND
                    | array
                    | command_call_with_parentheses"""
        p[0] = p[1]

    def p_command_call_with_parentheses(self, p):
        """command_call_with_parentheses : command_name eorws LPAREN argument_list RPAREN
           command_call_with_parentheses : command_name eorws LPAREN argument_list
           command_call_with_parentheses : command_name eorws LPAREN"""
        p[0] = CommandSpace(p[0], p[2:])


    def p_command_name(self, p):
        """command_name : PLAIN_STR
                        | COMMAND"""
        p[0] = p[1]

    def p_array(self, p):
        """array : LBRACE
           array : LBRACE argument_list
           array : LBRACE argument_list RBRACE"""
        if len(p) == 2:
            p[0] = Array()
        elif len(p) == 3:
            pass
        else:
            pass
        p[0] = p[1:]

    def p_eorws(self, p):
        """eorws : empty
                 | WHITESPACE"""
        p[0] = p[1]

    def p_empty(self, p):
        """empty :"""

    def p_error(self, p):
        raise exceptions.CommandError(f"Syntax error at '{p.value}'")

    def build(self, **kwargs):
        self.parser = yacc.yacc(module=self,
                                errorlog=yacc.NullLogger(), **kwargs)

    def parse(self, lexer: lex.Lexer, **kwargs) -> typing.Any:
        self.parser.parse(lexer=lexer, **kwargs)
        return self.parsed_line


def create_partial_parser(commands) -> InteractivePartialParser:
    command_parser = InteractivePartialParser(commands)
    command_parser.build(debug=False, write_tables=False)
    return command_parser
