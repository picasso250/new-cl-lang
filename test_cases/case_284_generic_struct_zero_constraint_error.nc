# ERROR: generic type Box: type arg Bad does not satisfy types.Zero

import types

struct Node { value: i32 }

struct Bad {
    ptr: *Node
}

struct Box[T types.Zero] {
    value: T
}

fun main() {
    let n = new Node { value: 1 }
    let _box = Box[Bad] { value: Bad { ptr: n } }
}
