"""词法分析器 —— NC 源码 → Token 流。"""

from dataclasses import dataclass
from enum import Enum, auto


class TokenKind(Enum):
    INTEGER = auto()
    IDENT = auto()
    # 关键字
    LET = auto()
    # 运算符
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    EQ = auto()
    # 分隔符
    LPAREN = auto()
    RPAREN = auto()
    SEMI = auto()
    EOF = auto()


@dataclass
class Token:
    kind: TokenKind
    value: str | int
    pos: int


KEYWORDS = {
    "let": TokenKind.LET,
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
        if ch == "(":
            yield Token(TokenKind.LPAREN, "(", i); i += 1; continue
        if ch == ")":
            yield Token(TokenKind.RPAREN, ")", i); i += 1; continue
        if ch == ";":
            yield Token(TokenKind.SEMI, ";", i); i += 1; continue

        raise SyntaxError(f"Unexpected character '{ch}' at position {i}")

    yield Token(TokenKind.EOF, "", n)
