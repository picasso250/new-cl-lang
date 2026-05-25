import io
# STDOUT: 3
fun choose(a: bool, b: bool): i32 {
    if a { 1 } else if b { 2 } else { 3 }
}

fun main() {
    io.println(choose(false, false))
}
