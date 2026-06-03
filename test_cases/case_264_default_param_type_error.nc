# ERROR: default parameter b: expected i32, got str

fun bad(a: i32, b: i32 = "x"): i32 {
    a + b
}

fun main() {
    bad(1)
}
