# ERROR: function bad: missing return i32
fun bad(): i32 {
    let x = 1
}

fun main() {
    print(bad())
}
