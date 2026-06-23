import io

# STDOUT: method bad

struct Box { value: i32 }

fun (b *Box) get(): i32 {
    if b.value < 0 {
        err "method bad"
    }
    ret b.value
}

fun main() {
    let b = new Box { value: -1 }
    try value = b.get() {
        io.println(value)
    } else e {
        io.println("method bad")
    }
}
