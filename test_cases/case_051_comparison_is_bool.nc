import io
# STDOUT: 1
fun is_big(x: i32): bool {
    return x > 10
}

fun main() {
    io.println(is_big(12))
}
