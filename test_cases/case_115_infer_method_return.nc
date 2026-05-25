import io
# STDOUT: 42

struct Box { value: i32 }

fun (b *Box) get() {
    b.value
}

fun main() {
    let b = new Box { value: 42 }
    io.println(b.get())
}
