# ERROR: function bad return type: expected i32, got str

fun bad() {
    if true { return 1 }
    return "x"
}

fun main() {
    bad()
}
