import typing

import ply.lex as lex


class CommandLanguageLexer:
    tokens = (
        "WHITESPACE",
        "COMMAND",
        "PLAIN_STR",
        "LPAREN",
        "RPAREN",
        "LBRACE",
        "RBRACE",
        "PIPE",
        "QUOTED_STR"
    )
    states = (
        ("interactive", "inclusive"),
    )

    def __init__(self, oneword_commands: typing.Sequence[str]) -> None:
        self.oneword_commands = dict.fromkeys(oneword_commands, "COMMAND")

    # Main(INITIAL) state
    t_ignore_WHITESPACE = r"\s+"
    t_LPAREN = r"\("
    t_RPAREN = r"\)"
    t_LBRACE = r"\["
    t_RBRACE = r"\]"
    t_PIPE = r"\|"

    def t_COMMAND(self, t):
        r"""\w+(\.\w+)+"""
        return t

    def t_QUOTED_STR(self, t):
        r"""
            \'+[^\']*\'+ |  # Single-quoted string
            \"+[^\"]*\"+    # Double-quoted string
        """
        return t

    def t_PLAIN_STR(self, t):
        r"""[^\|\[\]\(\)\s]+"""
        t.type = self.oneword_commands.get(t.value, "PLAIN_STR")
        return t

    # Interactive state
    t_interactive_WHITESPACE = r"\s+"

    def build(self, **kwargs):
        self.lexer = lex.lex(module=self,
                             errorlog=lex.NullLogger(), **kwargs)


def create_lexer(cmdstr: str, oneword_commands: typing.Sequence[str]) -> lex.Lexer:
    command_lexer = CommandLanguageLexer(oneword_commands)
    command_lexer.build()
    command_lexer.lexer.input(cmdstr)
    return command_lexer.lexer


def get_tokens(cmdstr: str, state="interactive") -> typing.List[lex.LexToken]:
    lexer = create_lexer(cmdstr, [])
    # Switching to the other state
    lexer.begin(state)
    return list(lexer)


class InteractiveLexer:
    def __init__(self, cmdstr: str, state="interactive"):
        self.tokens = get_tokens(cmdstr, state)



    def token(self):
        token = self.lexer.token()