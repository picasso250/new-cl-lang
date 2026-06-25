"""词法分析器 —— NC 源码 → Token 流。"""

from dataclasses import dataclass
from enum import Enum, auto


class TokenKind(Enum):
    INTEGER = auto()
    FLOAT = auto()
    STRING = auto()
    CHAR = auto()
    BOOL = auto()
    IDENT = auto()
    # 关键字
    LET = auto()
    IF = auto()
    ELSE = auto()
    TYPE = auto()
    FUN = auto()
    RET = auto()
    ERR = auto()
    TRY = auto()
    STRUCT = auto()
    IFACE = auto()
    ENUM = auto()
    MATCH = auto()
    FOR = auto()
    IN = auto()
    BREAK = auto()
    NEW = auto()
    DEFER = auto()
    NIL = auto()
    IMPORT = auto()
    EXTERN = auto()
    SPAWN = auto()
    # 运算符
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    AMP = auto()
    PIPE = auto()
    CARET = auto()
    TILDE = auto()
    SHL = auto()
    SHR = auto()
    EQ = auto()
    PLUSEQ = auto()
    MINUSEQ = auto()
    STAREQ = auto()
    SLASHEQ = auto()
    PERCENTEQ = auto()
    AMPEQ = auto()
    PIPEEQ = auto()
    CARETEQ = auto()
    SHLEQ = auto()
    SHREQ = auto()
    PLUSPLUS = auto()
    MINUSMINUS = auto()
    GT = auto()
    LT = auto()
    GE = auto()
    LE = auto()
    EQEQ = auto()
    NE = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    QUESTION = auto()
    QUESTIONQUESTION = auto()
    NOTNOT = auto()
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
    "ret": TokenKind.RET,
    "err": TokenKind.ERR,
    "try": TokenKind.TRY,
    "struct": TokenKind.STRUCT,
    "iface": TokenKind.IFACE,
    "enum": TokenKind.ENUM,
    "match": TokenKind.MATCH,
    "for": TokenKind.FOR,
    "in": TokenKind.IN,
    "break": TokenKind.BREAK,
    "new": TokenKind.NEW,
    "defer": TokenKind.DEFER,
    "nil": TokenKind.NIL,
    "import": TokenKind.IMPORT,
    "extern": TokenKind.EXTERN,
    "spawn": TokenKind.SPAWN,
    "type": TokenKind.TYPE,
    "true": TokenKind.BOOL,
    "false": TokenKind.BOOL,
}


INTEGER_SUFFIXES = {"i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64"}
FLOAT_SUFFIXES = {"f32", "f64"}


def _decode_escape(source: str, i: int, quote: str) -> tuple[str, int]:
    if i + 1 >= len(source):
        raise SyntaxError(f"Unterminated escape sequence at position {i}")
    ec = source[i + 1]
    if ec == 'n': return '\n', i + 2
    if ec == 't': return '\t', i + 2
    if ec == 'r': return '\r', i + 2
    if ec == '\\': return '\\', i + 2
    if ec == quote: return quote, i + 2
    if ec == '"': return '"', i + 2
    if ec == "'": return "'", i + 2
    if ec == 'u' and i + 2 < len(source) and source[i + 2] == "{":
        j = i + 3
        while j < len(source) and source[j] != "}":
            j += 1
        if j >= len(source):
            raise SyntaxError(f"Unterminated unicode escape at position {i}")
        digits = source[i + 3:j]
        if not digits:
            raise SyntaxError(f"Invalid unicode escape at position {i}")
        try:
            cp = int(digits, 16)
        except ValueError:
            raise SyntaxError(f"Invalid unicode escape at position {i}")
        if cp > 0x10FFFF or 0xD800 <= cp <= 0xDFFF:
            raise SyntaxError(f"Invalid unicode code point U+{cp:X} at position {i}")
        return chr(cp), j + 1
    return ec, i + 2


def _scan_interpolation_expr(source: str, i: int) -> tuple[str, int]:
    start = i
    depth = 1
    quote = None
    while i < len(source):
        ch = source[i]
        if quote:
            if ch == '\\':
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            i += 1
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if ch == "}":
                depth -= 1
                if depth == 0:
                    expr = source[start:i].strip()
                    if not expr:
                        raise SyntaxError(f"Empty string interpolation at position {start - 1}")
                    return expr, i + 1
            else:
                depth -= 1
                if depth < 1:
                    raise SyntaxError(f"Unbalanced string interpolation at position {start - 1}")
        i += 1
    raise SyntaxError(f"Unterminated string interpolation at position {start - 1}")


def _scan_string(source: str, start: int) -> tuple[str | tuple, int]:
    i = start + 1
    chars = []
    parts = []
    interpolated = False
    while i < len(source):
        ch = source[i]
        if ch == '"':
            i += 1
            literal = ''.join(chars)
            if interpolated:
                if literal:
                    parts.append(("literal", literal))
                return ("interpolated", parts), i
            return literal, i
        if ch == '\\':
            value, i = _decode_escape(source, i, '"')
            chars.append(value)
            continue
        if ch == "{":
            if i + 1 < len(source) and source[i + 1] == "{":
                chars.append("{")
                i += 2
                continue
            interpolated = True
            literal = ''.join(chars)
            if literal:
                parts.append(("literal", literal))
            chars = []
            expr, i = _scan_interpolation_expr(source, i + 1)
            parts.append(("expr", expr))
            continue
        if ch == "}":
            if i + 1 < len(source) and source[i + 1] == "}":
                chars.append("}")
                i += 2
                continue
            raise SyntaxError(f"Unescaped '}}' in string literal at position {i}")
        chars.append(ch)
        i += 1
    raise SyntaxError(f"Unterminated string literal at position {start}")


def _scan_char(source: str, start: int) -> tuple[int, int]:
    i = start + 1
    if i >= len(source):
        raise SyntaxError(f"Unterminated char literal at {start}")
    if source[i] == "'":
        raise SyntaxError(f"Empty char literal at position {start}")
    if source[i] == '\\':
        value, i = _decode_escape(source, i, "'")
    else:
        value = source[i]
        i += 1
    if i >= len(source) or source[i] != "'":
        raise SyntaxError(f"Char literal must contain exactly one Unicode code point at position {start}")
    if len(value) != 1:
        raise SyntaxError(f"Char literal must contain exactly one Unicode code point at position {start}")
    return ord(value), i + 1


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
            is_float = False
            if i < n and source[i] == "." and not (i + 1 < n and source[i + 1] == "."):
                is_float = True
                i += 1
                if i >= n or not source[i].isdigit():
                    raise SyntaxError(f"Invalid float literal at position {start}")
                while i < n and source[i].isdigit():
                    i += 1
            suffix_start = i
            while i < n and (source[i].isalnum() or source[i] == "_"):
                i += 1
            suffix = source[suffix_start:i] or None
            if is_float:
                if suffix is not None and suffix not in FLOAT_SUFFIXES:
                    raise SyntaxError(f"Invalid float literal suffix '{suffix}' at position {suffix_start}")
                yield Token(TokenKind.FLOAT, (source[start:suffix_start], suffix), start)
            else:
                if suffix is not None and suffix not in INTEGER_SUFFIXES:
                    raise SyntaxError(f"Invalid integer literal suffix '{suffix}' at position {suffix_start}")
                yield Token(TokenKind.INTEGER, (int(source[start:suffix_start]), suffix), start)
            continue

        # 字符串
        if ch == '"':
            value, i = _scan_string(source, i)
            yield Token(TokenKind.STRING, value, i)
            continue

        # 字符字面量
        if ch == "'":
            val, i = _scan_char(source, i)
            yield Token(TokenKind.CHAR, val, i)
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

        if i + 2 < n:
            three = source[i:i+3]
            if three == "<<=":
                yield Token(TokenKind.SHLEQ, "<<=", i); i += 3; continue
            if three == ">>=":
                yield Token(TokenKind.SHREQ, ">>=", i); i += 3; continue

        # 双字符符号（先试两字符）
        if i + 1 < n:
            two = source[i:i+2]
            if two == "+=":
                yield Token(TokenKind.PLUSEQ, "+=", i); i += 2; continue
            if two == "-=":
                yield Token(TokenKind.MINUSEQ, "-=", i); i += 2; continue
            if two == "*=":
                yield Token(TokenKind.STAREQ, "*=", i); i += 2; continue
            if two == "/=":
                yield Token(TokenKind.SLASHEQ, "/=", i); i += 2; continue
            if two == "%=":
                yield Token(TokenKind.PERCENTEQ, "%=", i); i += 2; continue
            if two == "&=":
                yield Token(TokenKind.AMPEQ, "&=", i); i += 2; continue
            if two == "|=":
                yield Token(TokenKind.PIPEEQ, "|=", i); i += 2; continue
            if two == "^=":
                yield Token(TokenKind.CARETEQ, "^=", i); i += 2; continue
            if two == "++":
                yield Token(TokenKind.PLUSPLUS, "++", i); i += 2; continue
            if two == "--":
                yield Token(TokenKind.MINUSMINUS, "--", i); i += 2; continue
            if two == "<<":
                yield Token(TokenKind.SHL, "<<", i); i += 2; continue
            if two == ">>":
                yield Token(TokenKind.SHR, ">>", i); i += 2; continue
            if two == ">=":
                yield Token(TokenKind.GE, ">=", i); i += 2; continue
            if two == "<=":
                yield Token(TokenKind.LE, "<=", i); i += 2; continue
            if two == "==":
                yield Token(TokenKind.EQEQ, "==", i); i += 2; continue
            if two == "!=":
                yield Token(TokenKind.NE, "!=", i); i += 2; continue
            if two == "!!":
                yield Token(TokenKind.NOTNOT, "!!", i); i += 2; continue
            if two == "&&":
                yield Token(TokenKind.AND, "&&", i); i += 2; continue
            if two == "||":
                yield Token(TokenKind.OR, "||", i); i += 2; continue
            if two == "::":
                yield Token(TokenKind.COLONCOLON, "::", i); i += 2; continue
            if two == "->":
                yield Token(TokenKind.ARROW, "->", i); i += 2; continue
            if two == "??":
                yield Token(TokenKind.QUESTIONQUESTION, "??", i); i += 2; continue

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
        if ch == "&":
            yield Token(TokenKind.AMP, "&", i); i += 1; continue
        if ch == "|":
            yield Token(TokenKind.PIPE, "|", i); i += 1; continue
        if ch == "^":
            yield Token(TokenKind.CARET, "^", i); i += 1; continue
        if ch == "~":
            yield Token(TokenKind.TILDE, "~", i); i += 1; continue
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
        if ch == "?":
            yield Token(TokenKind.QUESTION, "?", i); i += 1; continue

        raise SyntaxError(f"Unexpected character '{ch}' at position {i}")

    yield Token(TokenKind.EOF, "", n)
