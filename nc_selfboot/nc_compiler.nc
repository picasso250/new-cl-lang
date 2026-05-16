enum TokenKind { Integer, Ident, Plus, LParen, RParen, Semi, Eof }

struct Token {
    kind: TokenKind,
    value: str,
    pos: i32
}

fun main() {
    let tok = Token { kind: TokenKind::Integer, value: "42", pos: 0 }
    if tok.kind == TokenKind::Integer { print("ok") }
}
