# ERROR: generic function use_zero: type arg Bad does not satisfy types.Zero

import types

struct Node { value: i32 }

struct Bad {
    ptr: *Node
}

fun use_zero[T types.Zero](x: T): T { x }

fun main() {
    let n = new Node { value: 1 }
    use_zero[Bad](Bad { ptr: n })
}
