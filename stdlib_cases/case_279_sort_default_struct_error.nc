# ERROR: generic function sort.sort: type arg Item does not satisfy types.Cmp

import sort

struct Item { key: i32 }

fun main() {
    let xs = []Item { Item { key: 2 }, Item { key: 1 } }
    sort.sort[Item](xs)
}
