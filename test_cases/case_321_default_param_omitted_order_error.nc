# ERROR: function bad: required parameter b cannot follow default parameter

fun bad(a = 1, b: i32): i32 {
    a + b
}

fun main() {
    bad(1, 2)
}
