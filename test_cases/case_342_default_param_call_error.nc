# ERROR: default parameter x: function calls are not allowed

fun make(): i32 {
    1
}

fun bad(x: i32 = make()): i32 {
    x
}

fun main() {
    bad()
}
