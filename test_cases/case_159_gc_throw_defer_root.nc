import runtime
import io
# STDOUT: 1

fun fail() {
    defer { runtime.gc_collect() }
    err str(1)
}

fun main() {
    if fail() is err {
        runtime.gc_collect()
        io.println(1)
    }
}
