# ERROR: generic function use_hash: type arg Bad does not satisfy types.Hash

import types

struct Bad {
    score: f64
}

fun use_hash[T types.Hash](x: T): T { x }

fun main() {
    use_hash[Bad](Bad { score: 1.5 })
}
