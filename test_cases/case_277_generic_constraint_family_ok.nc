import io
import types

struct Key {
    id: i32,
    name: str,
    active: bool
}

fun same[T types.Eq](a: T, b: T): bool { a == b }
fun hash_id[T types.Hash](x: T): i32 { x.id }
fun zero_len[T types.Zero](xs: []T): i32 { len(xs) }
fun min_ord[T types.Ord](a: T, b: T): T { if a < b { a } else { b } }

fun main() {
    io.println(same[Key](Key { id: 1, name: "a", active: true }, Key { id: 1, name: "a", active: true }))
    io.println(hash_id[Key](Key { id: 2, name: "b", active: false }))
    let nested = [][]i32 { []i32 { 1 } }
    io.println(zero_len[[]i32](nested))
    io.println(min_ord[u64](u64(9), u64(4)))
}

# STDOUT: 1
# STDOUT: 2
# STDOUT: 1
# STDOUT: 4
