# ERROR: Expected TokenKind.LBRACE

fun fail(): i32 {
    err "bad"
}

fun main() {
    if fail() is err {
    }
}
