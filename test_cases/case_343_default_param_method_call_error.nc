# ERROR: default parameter x: method calls are not allowed

struct Box { value: i32 }

fun (b *Box) get(): i32 {
    b.value
}

fun bad(b: *Box, x: i32 = b.get()): i32 {
    x
}

fun main() {
    let b = new Box { value: 1 }
    bad(b)
}
