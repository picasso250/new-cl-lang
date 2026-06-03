import io
import types

struct Pair[T types.Hash] {
    key: T
}

struct Key {
    id: i32,
    label: str
}

fun main() {
    let p = Pair[Key] { key: Key { id: 7, label: "x" } }
    io.println(p.key.id)
}

# STDOUT: 7
