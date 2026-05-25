import io
# ERROR: function bad tail expression: expected i32, got str
fun bad(): i32 {
    if true { "bad" } else { "worse" }
}

fun main() {
    io.println(bad())
}
