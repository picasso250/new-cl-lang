# STDOUT: one
fun describe(n: i32): str {
    match n {
        0 -> "zero"
        1 -> "one"
        else -> "many"
    }
}

fun main() {
    print(describe(1))
}
