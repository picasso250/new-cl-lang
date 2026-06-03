# ERROR: Variable 'b' not found

fun bad(a: i32 = b, b: i32 = 1): i32 {
    a + b
}

fun main() {
    bad()
}
