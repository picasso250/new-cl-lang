import io
# STDOUT: 4
fun add1(x: i32): i32 {
    x + 1
}

fun main() {
    io.println(add1(if true { 3 } else { 5 }))
}
