# ERROR: extern v1 does not support varargs

extern "c" {
    fun printf(fmt: *u8, ...)
}

fun main() {}
