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
        self.completed = False
        self.text = None

    def p_command_call(self, p):
        """command_line : empty
                        | argument_list
                        | command_call_no_parentheses
                        | command_call_with_parentheses"""
        if p[1]:
            self.text = p[1]
        else:
            self.text = [('text', "")]

    def p_command_call_no_parentheses(self, p):
        """command_call_no_parentheses : corps eorws argument_list eorws"""
        command, params = p[1]
        st = [p[2], *p[3], p[4]]

        stuff = [command] + [s for s in st if s]
        if stuff[-1][1].isspace():
            args = p[3] + [("text", "")]
        else:
            args = p[3]
        rem_params = params[len(args):]

        remhelp = self.get_remhelp(rem_params)
        rem_text = [("commander_hint", " ")]
        rem_text += [("commander_hint", " ".join(remhelp))]
        pt = [*stuff, *rem_text]
        p[0] = pt

    def p_arglist(self, p):
        """arglist : eorws argument_list eorws"""
        args = [arg for arg in [p[1], *p[2], p[3]] if arg]
        if args[-1][1].isspace():
            args.append(("text", ""))
        p[0] = args

    def p_argument_list(self, p):
        """argument_list : empty
                         | argument
                         | argument_list eorws argument"""
        if len(p) == 2:
            p[0] = [] if p[1] is None else [p[1]]
        else:
            p[0] = p[1]
            p[0].append(("text", p[2][1] + p[3][1]))

    def p_argument(self, p):
        """argument : PLAIN_STR
                    | QUOTED_STR
                    | COMMAND
                    | array
                    | command_call_with_parentheses"""
        if isinstance(p[1], list):
            p[0] = p[1]
        else:
            p[0] = ("text", p[1])

    def p_command_call_with_parentheses(self, p):
        """command_call_with_parentheses : corps eorws lparen arglist rparen eorws
           command_call_with_parentheses : corps eorws lparen arglist
           command_call_with_parentheses : corps eorws lparen eorws"""
        command, params = p[1]

        if len(p) == 7:
            text = [command, *p[2:4], *p[4], *p[5:7]]
        elif len(p) == 5:
            rem_params = params[len(p[4]):]
            remhelp = self.get_remhelp(rem_params)
            if remhelp:
                rem_text = [("commander_hint", " ")]
                rem_text += [("commander_hint", " ".join(remhelp))]
                text = [command, *p[2:4], *p[4], *rem_text, ("text", ")")]
            else:
                text = [command, *p[2:4], *p[4], ("text", ")")]
        else:
            self.completed = True
            remhelp = self.get_remhelp(params)
            rem_text = ("commander_hint", " ".join(remhelp))
            text = [command, *p[2:5], rem_text, ("text", ")")]
        # print([textm for textm in text if textm])
        p[0] = [textm for textm in text if textm]


    def p_corps(self, p):
        """corps : PLAIN_STR
                 | COMMAND"""
        p[0] = self.check_command(p[1])

    def p_array(self, p):
        """array : lbrace
           array : lbrace argument_list
           array : lbrace argument_list rbrace"""
        if len(p) == 4:
            p[0] = [*p[1], *p[2], *p[3]]
        elif len(p) == 3:
            p[0] = [*p[1], *p[2]]
        else:
            p[0] = [*p[1]]

    def p_lbrace(self, p):
        """lbrace : LBRACE
           rbrace : RBRACE
           lparen : LPAREN
           rparen : RPAREN"""
        mao = {"(": ")", "[": "]"}
        if self.autoclosing:
            p[0] = [("text", p[1]), ("text", mao[p[1]])]
        else:
            p[0] = [("text", p[1])]

    def p_eorws(self, p):
        """eorws : empty
                 | WHITESPACE"""
        if p[1] is None:
            p[0] = ()
        else:
            p[0] = ("text", p[1])

    def p_empty(self, p):
        """empty :"""

    def p_error(self, p):
        raise exceptions.CommandError(f"Syntax error at '{p.value}'")


    def check_command(self, command):
        if command in self.commands:
            command_text = ("commander_command", command)
            params = self.commands[command].paramtypes
        else:
            command_text = ("commander_invalid", command)
            params = []
        return command_text, params

    def get_remhelp(self, rem_params):
        remhelp: typing.List[str] = []
        for x in rem_params:
            remt = mitmproxy.types.CommandTypes.get(x, None)
            remhelp.append(remt.display)
        return remhelp

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
