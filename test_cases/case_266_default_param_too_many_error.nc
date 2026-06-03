# ERROR: add: expected 1 to 2 args, got 3

fun add(a: i32, b: i32 = 0): i32 {
    a + b
}

fun main() {
    add(1, 2, 3)
}
