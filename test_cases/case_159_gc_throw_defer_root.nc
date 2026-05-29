import runtime
import io
# STDOUT: 1

fun fail() {
    defer { runtime.gc_collect() }
    throw str(1)
}

fun main() {
    try {
        fail()
    } catch e {
        runtime.gc_collect()
        io.println(e)
    }
}
