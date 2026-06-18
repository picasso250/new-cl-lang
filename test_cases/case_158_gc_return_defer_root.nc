import runtime
import io
# STDOUT: 1

fun make(): str {
    defer { runtime.gc_collect() }
    ret str(1)
}

fun main() {
    let s = make()
    io.println(s)
}
