import typing

import ply.lex as lex
import ply.yacc as yacc

from mitmproxy import exceptions
from mitmproxy.language.lexer import CommandLanguageLexer
import mitmproxy.types

class InteractivePartialParser:
    # the list of possible tokens is always required
    tokens = CommandLanguageLexer.tokens

    def __init__(self, commands):
        self.commands = commands
        self.text = None

    def p_command_call(self, p):
        """command_line : empty
                        | command_call_no_parentheses
                        | command_call_with_parentheses"""
        if p[1]:
            self.text = p[1]
        else:
            self.text = [('text', "")]

    def p_command_call_no_parentheses(self, p):
        """command_call_no_parentheses : corps argument_list"""
        command, params = self.check_command(p[1])
        rem_params = params[len(p[2]):]

        remhelp: typing.List[str] = []
        for x in rem_params:
            remt = mitmproxy.types.CommandTypes.get(x, None)
            remhelp.append(remt.display)
        rem_text = ("commander_hint", " ".join(remhelp))
        p[0] = [command, *p[2], rem_text]

    def p_argument_list(self, p):
        """argument_list : empty
                         | argument
                         | argument_list argument"""
        if len(p) == 2:
            p[0] = [] if p[1] is None else [p[1]]
        else:
            p[0] = p[1]
            p[0].append(p[2])

    def p_argument(self, p):
        """argument : PLAIN_STR
                    | QUOTED_STR
                    | COMMAND
                    | command_call_with_parentheses"""
        if isinstance(p[1], list):
            p[0] = p[1]
        else:
            p[0] = ("text", p[1])

    def p_command_call_with_parentheses(self, p):
        """command_call_with_parentheses : corps LPAREN argument_list RPAREN
           command_call_with_parentheses : corps LPAREN argument_list
           command_call_with_parentheses : corps LPAREN"""

        command, params = self.check_command(p[1])
        if len(p) == 5:
            text = [command, ("text", "("), *p[3], ("text", ")")]
        elif len(p) == 4:
            rem_params = params[len(p[3]):]
            remhelp: typing.List[str] = []
            for x in rem_params:
                remt = mitmproxy.types.CommandTypes.get(x, None)
                remhelp.append(remt.display)
            if " ".join(remhelp):
                rem_text = ("commander_hint", " ".join(remhelp))
                text = [command, ("text", "("), *p[3], rem_text, ("text", ")")]
            else:
                text = [command, ("text", "("), *p[3], ("text", ")")]
        else:
            remhelp: typing.List[str] = []
            for x in params:
                remt = mitmproxy.types.CommandTypes.get(x, None)
                remhelp.append(remt.display)
            rem_text = ("commander_hint", " ".join(remhelp))
            text = [command, ("text", "("), rem_text, ("text", ")")]
        p[0] = text

    def p_corps(self, p):
        """corps : PLAIN_STR
                 | COMMAND"""
        p[0] = p[1]

    def p_empty(self, p):
        """empty :"""

    def p_error(self, p):
        for i, t in enumerate(self.text):
            self.text[i][0] = "commander_invalid"


    def check_command(self, command):
        if command in self.commands:
            command_text = ("commander_command", command)
            params = self.commands[command].paramtypes
        else:
            command_text = ("commander_invalid", command)
            params = []
        return command_text, params


    def build(self, **kwargs):
        self.parser = yacc.yacc(module=self,
                                errorlog=yacc.NullLogger(), **kwargs)

    def parse(self, lexer: lex.Lexer, **kwargs) -> typing.Any:
        self.parser.parse(lexer=lexer, **kwargs)
        return self.text


def create_partial_parser(commands) -> InteractivePartialParser:
    command_parser = InteractivePartialParser(commands)
    command_parser.build(debug=False, write_tables=False)
    return command_parser
