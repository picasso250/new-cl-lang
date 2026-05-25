import io
# ERROR: argument x to takes_i32: expected i32, got str
fun takes_i32(x: i32): i32 {
    return x
}

fun main() {
    io.println(takes_i32("bad"))
}
