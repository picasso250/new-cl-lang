import io
# STDOUT: 9

fun main() {
    io.println(next(8))
}

fun next(x: i32) {
    inc(x)
}

fun inc(x: i32) {
    x + 1
}
