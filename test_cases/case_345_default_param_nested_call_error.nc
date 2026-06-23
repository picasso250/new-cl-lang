# ERROR: default parameter b: function calls are not allowed

struct Box { value: i32 }

fun make(): i32 {
    1
}

fun bad(b: Box = Box { value: make() }): i32 {
    b.value
}

fun main() {
    bad()
}
