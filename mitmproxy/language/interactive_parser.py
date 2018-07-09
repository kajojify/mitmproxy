import typing

import ply.lex as lex
import ply.yacc as yacc

from mitmproxy import exceptions
from mitmproxy.language import structures
from mitmproxy.language.lexer import CommandLanguageLexer


class InteractivePartialParser:
    # the list of possible tokens is always required
    tokens = CommandLanguageLexer.tokens

    def __init__(self, manager):
        self.manager = manager
        self.parsed_line = None

    def p_command_call(self, p):
        """command_line : empty
                        | eorws expression eorws optional_pipes eorws"""
        self.parsed_line = structures.CommandLine(p[1:])

    def p_expression(self, p):
        """expression : array
                      | command_call_no_parentheses
                      | command_call_with_parentheses"""
        p[0] = p[1]

    def p_pipes(self, p):
        """optional_pipes : pipe_expression optional_pipes
           optional_pipes : pipe_expression"""
        p[0] = p[1]

    def p_pipe_expression(self, p):
        """pipe_expression : empty
                           | PIPE eorws
                           | PIPE eorws command_call"""
        p[0] = [p[1]] if p[1] else []
        if len(p) > 2:
            p[0].extend(p[2:])

    def p_command_calll(self, p):
        """command_call : command_call_no_parentheses
                        | command_call_with_parentheses"""
        p[0] = p[1]

    def p_command_call_with_parentheses(self, p):
        """command_call_with_parentheses : command_name eorws LPAREN eorws
           command_call_with_parentheses : command_name eorws LPAREN eorws argument_list eorws
           command_call_with_parentheses : command_name eorws LPAREN eorws argument_list eorws RPAREN"""
        p[0] = structures.CommandSpace(p[1], p[2:], self.manager)

    def p_command_call_no_parentheses(self, p):
        """command_call_no_parentheses : command_name eorws argument_list"""
        p[0] = structures.CommandSpace(p[1], p[2:], self.manager)

    def p_array(self, p):
        """array : LBRACE eorws
           array : LBRACE eorws RBRACE
           array : LBRACE eorws argument_list eorws
           array : LBRACE eorws argument_list eorws RBRACE"""
        if len(p) == 3:
            p[0] = structures.Array(space=p[1:], autoclosing=True)
        elif len(p) == 4:
            p[0] = structures.Array(space=p[1:])
        else:
            p[0] = structures.Array(space=[*p[1:3], *p[3], *p[4:]])

    def p_argument_list(self, p):
        """argument_list : empty
                         | argument
                         | argument_list eorws argument"""
        if len(p) == 2:
            p[0] = [] if p[1] is None else [p[1]]
        else:
            p[0] = p[1]
            p[0].append(p[2])
            p[0].append(p[3])

    def p_argument(self, p):
        """argument : PLAIN_STR
                    | QUOTED_STR
                    | COMMAND
                    | array
                    | command_call_with_parentheses"""
        p[0] = p[1]

    def p_command_name(self, p):
        """command_name : PLAIN_STR
                        | COMMAND"""
        p[0] = p[1]

    def p_eorws(self, p):
        """eorws : empty
                 | WHITESPACE"""
        p[0] = p[1]

    def p_empty(self, p):
        """empty :"""

    def p_error(self, p):
        raise exceptions.CommandError("Syntax error")

    def build(self, **kwargs):
        self.parser = yacc.yacc(module=self,
                                errorlog=yacc.NullLogger(), **kwargs)

    def parse(self, lexer: lex.Lexer, **kwargs) -> typing.Any:
        self.parser.parse(lexer=lexer, **kwargs)
        return self.parsed_line


def create_partial_parser(manager) -> InteractivePartialParser:
    command_parser = InteractivePartialParser(manager)
    command_parser.build(debug=False, write_tables=False)
    return command_parser
