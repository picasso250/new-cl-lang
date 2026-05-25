import io
# STDOUT: one
fun describe(n: i32): str {
    match n {
        0 -> "zero"
        1 -> "one"
        else -> "many"
    }
}

fun main() {
    io.println(describe(1))
}
