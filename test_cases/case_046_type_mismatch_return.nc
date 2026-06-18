import io
# ERROR: ret: expected i32, got str
fun bad(): i32 {
    ret "bad"
}

fun main() {
    io.println(bad())
}
