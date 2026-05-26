import io
# STDOUT: 1

fun fail() {
    defer { gc_collect() }
    throw str(1)
}

fun main() {
    try {
        fail()
    } catch e {
        gc_collect()
        io.println(e)
    }
}
