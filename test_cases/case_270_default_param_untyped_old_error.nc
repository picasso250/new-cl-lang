# ERROR: Expected TokenKind.COLON

fun bad(a, b = 0): i32 {
    a + b
}

fun main() {
    bad(1)
}
