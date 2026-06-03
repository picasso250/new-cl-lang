# ERROR: add: expected 2 to 3 args, got 1

fun add(a: i32, b: i32, c: i32 = 0): i32 {
    a + b + c
}

fun main() {
    add(1)
}
