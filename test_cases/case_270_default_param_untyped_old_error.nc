# ERROR: parameter type is required unless a default value is provided

fun bad(a, b = 0): i32 {
    a + b
}

fun main() {
    bad(1)
}
