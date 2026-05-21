# STDOUT: 4
fun id(x: i32): i32 {
    return x
}

fun main() {
    let name = "nc"
    print(id(match name {
        "c" -> 1
        "nc" -> 4
        else -> 0
    }))
}
