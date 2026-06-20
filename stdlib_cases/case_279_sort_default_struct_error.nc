# ERROR: comparison: expected numeric operands, got Item and Item

import sort

struct Item { key: i32 }

fun main() {
    let xs = []Item { Item { key: 2 }, Item { key: 1 } }
    sort.sort[Item](xs)
}
