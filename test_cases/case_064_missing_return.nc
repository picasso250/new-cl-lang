import io
# ERROR: function bad: missing ret i32
fun bad(): i32 {
    let x = 1
}

fun main() {
    io.println(bad())
}
