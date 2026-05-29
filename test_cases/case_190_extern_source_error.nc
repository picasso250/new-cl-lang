# ERROR: extern v1 only supports "c"

extern "foo.c" {
    fun putchar(c: i32): i32
}

fun main() {}
