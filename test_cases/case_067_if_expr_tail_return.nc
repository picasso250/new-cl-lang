# STDOUT: 3
fun choose(b: bool): i32 {
    if b { 1 } else { 3 }
}

fun main() {
    print(choose(false))
}
