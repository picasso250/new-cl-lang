import io
# STDOUT: 1

fun make(): str {
    defer { gc_collect() }
    return str(1)
}

fun main() {
    let s = make()
    io.println(s)
}
