import runtime
import io
# STDOUT: 1

fun fail() {
    defer { runtime.gc_collect() }
    err str(1)
}

fun main() {
    try fail() {
        io.println(0)
    } else e {
        runtime.gc_collect()
        io.println(1)
    }
}
