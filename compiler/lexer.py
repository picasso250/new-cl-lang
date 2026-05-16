"""词法分析器 —— NC 源码 → Token 流。"""

from dataclasses import dataclass
from enum import Enum, auto


class TokenKind(Enum):
    INTEGER = auto()
    IDENT = auto()
    # 关键字
    LET = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    FUN = auto()
    RETURN = auto()
    # 运算符
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    EQ = auto()
    GT = auto()
    LT = auto()
    GE = auto()
    LE = auto()
    EQEQ = auto()
    NE = auto()
    # 分隔符
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    SEMI = auto()
    COMMA = auto()
    COLON = auto()
    EOF = auto()


@dataclass
class Token:
    kind: TokenKind
    value: str | int
    pos: int


KEYWORDS = {
    "let": TokenKind.LET,
    "if": TokenKind.IF,
    "else": TokenKind.ELSE,
    "while": TokenKind.WHILE,
    "fun": TokenKind.FUN,
    "return": TokenKind.RETURN,
}


def lex(source: str):
    """生成器，逐 token 产出。"""
    i = 0
    n = len(source)

    while i < n:
        ch = source[i]

        # 空白
        if ch in " \t\n\r":
            i += 1
            continue

        # 注释（# 到行尾）
        if ch == "#":
            while i < n and source[i] != "\n":
                i += 1
            continue

        # 数字
        if ch.isdigit():
            start = i
            while i < n and source[i].isdigit():
                i += 1
            yield Token(TokenKind.INTEGER, int(source[start:i]), start)
            continue

        # 标识符 / 关键字
        if ch.isalpha() or ch == "_":
            start = i
            while i < n and (source[i].isalnum() or source[i] == "_"):
                i += 1
            word = source[start:i]
            kind = KEYWORDS.get(word, TokenKind.IDENT)
            yield Token(kind, word, start)
            continue

        # 双字符符号（先试两字符）
        if i + 1 < n:
            two = source[i:i+2]
            if two == ">=":
                yield Token(TokenKind.GE, ">=", i); i += 2; continue
            if two == "<=":
                yield Token(TokenKind.LE, "<=", i); i += 2; continue
            if two == "==":
                yield Token(TokenKind.EQEQ, "==", i); i += 2; continue
            if two == "!=":
                yield Token(TokenKind.NE, "!=", i); i += 2; continue

        # 单字符符号
        if ch == "+":
            yield Token(TokenKind.PLUS, "+", i); i += 1; continue
        if ch == "-":
            yield Token(TokenKind.MINUS, "-", i); i += 1; continue
        if ch == "*":
            yield Token(TokenKind.STAR, "*", i); i += 1; continue
        if ch == "/":
            yield Token(TokenKind.SLASH, "/", i); i += 1; continue
        if ch == "%":
            yield Token(TokenKind.PERCENT, "%", i); i += 1; continue
        if ch == "=":
            yield Token(TokenKind.EQ, "=", i); i += 1; continue
        if ch == ">":
            yield Token(TokenKind.GT, ">", i); i += 1; continue
        if ch == "<":
            yield Token(TokenKind.LT, "<", i); i += 1; continue
        if ch == "(":
            yield Token(TokenKind.LPAREN, "(", i); i += 1; continue
        if ch == ")":
            yield Token(TokenKind.RPAREN, ")", i); i += 1; continue
        if ch == "{":
            yield Token(TokenKind.LBRACE, "{", i); i += 1; continue
        if ch == "}":
            yield Token(TokenKind.RBRACE, "}", i); i += 1; continue
        if ch == ";":
            yield Token(TokenKind.SEMI, ";", i); i += 1; continue
        if ch == ",":
            yield Token(TokenKind.COMMA, ",", i); i += 1; continue
        if ch == ":":
            yield Token(TokenKind.COLON, ":", i); i += 1; continue

        raise SyntaxError(f"Unexpected character '{ch}' at position {i}")

    yield Token(TokenKind.EOF, "", n)
