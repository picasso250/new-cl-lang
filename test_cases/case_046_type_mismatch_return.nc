import io
# ERROR: return: expected i32, got str
fun bad(): i32 {
    return "bad"
}

fun main() {
    io.println(bad())
}
