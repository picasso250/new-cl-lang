import io
# STDOUT: 3
fun choose(b: bool): i32 {
    if b { 1 } else { 3 }
}

fun main() {
    io.println(choose(false))
}
