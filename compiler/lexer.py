"""词法分析器 —— NC 源码 → Token 流。"""

from dataclasses import dataclass
from enum import Enum, auto


class TokenKind(Enum):
    INTEGER = auto()
    STRING = auto()
    CHAR = auto()
    BOOL = auto()
    IDENT = auto()
    # 关键字
    LET = auto()
    IF = auto()
    ELSE = auto()
    FUN = auto()
    RETURN = auto()
    STRUCT = auto()
    ENUM = auto()
    SWITCH = auto()
    FOR = auto()
    IN = auto()
    BREAK = auto()
    NEW = auto()
    TRY = auto()
    CATCH = auto()
    THROW = auto()
    DEFER = auto()
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
    AND = auto()
    OR = auto()
    NOT = auto()
    # 分隔符
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    SEMI = auto()
    COMMA = auto()
    COLON = auto()
    COLONCOLON = auto()
    DOTDOT = auto()
    ARROW = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    DOT = auto()
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
    "fun": TokenKind.FUN,
    "return": TokenKind.RETURN,
    "struct": TokenKind.STRUCT,
    "enum": TokenKind.ENUM,
    "switch": TokenKind.SWITCH,
    "for": TokenKind.FOR,
    "in": TokenKind.IN,
    "break": TokenKind.BREAK,
    "new": TokenKind.NEW,
    "try": TokenKind.TRY,
    "catch": TokenKind.CATCH,
    "throw": TokenKind.THROW,
    "defer": TokenKind.DEFER,
    "true": TokenKind.BOOL,
    "false": TokenKind.BOOL,
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

        # 字符串
        if ch == '"':
            i += 1
            chars = []
            while i < n and source[i] != '"':
                if source[i] == '\\' and i + 1 < n:
                    ec = source[i + 1]
                    if ec == 'n': chars.append('\n')
                    elif ec == 't': chars.append('\t')
                    elif ec == 'r': chars.append('\r')
                    elif ec == '\\': chars.append('\\')
                    elif ec == '"': chars.append('"')
                    else: chars.append(source[i]); chars.append(ec)
                    i += 2
                else:
                    chars.append(source[i])
                    i += 1
            value = ''.join(chars)
            if i < n:
                i += 1
            yield Token(TokenKind.STRING, value, i - len(value) - 2)
            continue

        # 字符字面量
        if ch == "'":
            i += 1
            if i >= n: raise SyntaxError(f"Unterminated char literal at {i}")
            if source[i] == '\\' and i + 1 < n:
                ec = source[i + 1]
                if ec == 'n': val = 10
                elif ec == 't': val = 9
                elif ec == 'r': val = 13
                elif ec == '\\': val = 92
                elif ec == "'" : val = 39
                elif ec == '"': val = 34
                else: val = ord(ec)
                i += 2
            else:
                val = ord(source[i])
                i += 1
            if i >= n or source[i] != "'": raise SyntaxError(f"Unterminated char literal at {i}")
            i += 1
            yield Token(TokenKind.CHAR, val, i - 3)
            continue
        if ch.isalpha() or ch == "_":
            start = i
            while i < n and (source[i].isalnum() or source[i] == "_"):
                i += 1
            word = source[start:i]
            kind = KEYWORDS.get(word, TokenKind.IDENT)
            value = (word == "true") if kind == TokenKind.BOOL else word
            yield Token(kind, value, start)
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
            if two == "&&":
                yield Token(TokenKind.AND, "&&", i); i += 2; continue
            if two == "||":
                yield Token(TokenKind.OR, "||", i); i += 2; continue
            if two == "::":
                yield Token(TokenKind.COLONCOLON, "::", i); i += 2; continue
            if two == "->":
                yield Token(TokenKind.ARROW, "->", i); i += 2; continue

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
        if ch == ".":
            if i + 1 < n and source[i + 1] == ".":
                yield Token(TokenKind.DOTDOT, "..", i); i += 2; continue
            yield Token(TokenKind.DOT, ".", i); i += 1; continue
        if ch == "[":
            yield Token(TokenKind.LBRACKET, "[", i); i += 1; continue
        if ch == "]":
            yield Token(TokenKind.RBRACKET, "]", i); i += 1; continue
        if ch == "!":
            yield Token(TokenKind.NOT, "!", i); i += 1; continue

        raise SyntaxError(f"Unexpected character '{ch}' at position {i}")

    yield Token(TokenKind.EOF, "", n)
