import io
# STDOUT: 4
fun id(x: i32): i32 {
    ret x
}

fun main() {
    let name = "nc"
    io.println(id(match name {
        "c" -> 1
        "nc" -> 4
        else -> 0
    }))
}
