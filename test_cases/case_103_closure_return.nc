import io
# STDOUT: 12
fun make_add(base: i32): (i32) -> i32 {
    fun(x: i32): i32 { x + base }
}

fun main() {
    let add = make_add(7)
    io.println(add(5))
}
