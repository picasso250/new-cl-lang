# ERROR: function bad ret type: expected i32, got str

fun bad() {
    if true { ret 1 }
    ret "x"
}

fun main() {
    bad()
}
