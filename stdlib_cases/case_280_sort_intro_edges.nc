import io
import sort

struct Item { key: i32, seq: i32 }

fun main() {
    let less_i32 = fun(a: i32, b: i32): bool { a < b }
    let less_item = fun(a: Item, b: Item): bool { a.key < b.key }

    let empty = []i32 {}
    sort.sort[i32](empty)
    io.println(len(empty))

    let one = []i32 { 7 }
    sort.sort[i32](one)
    io.println(one[0])

    let xs = []i32 {
        32, 31, 30, 29, 28, 27, 26, 25,
        24, 23, 22, 21, 20, 19, 18, 17,
        16, 15, 14, 13, 12, 11, 10, 9,
        8, 7, 6, 5, 4, 3, 2, 1
    }
    sort.sort[i32](xs)
    io.println(xs[0])
    io.println(xs[15])
    io.println(xs[31])
    io.println(sort.is_sorted_by[i32](xs, less_i32))

    let items = []Item {
        Item { key: 3, seq: 0 },
        Item { key: 1, seq: 1 },
        Item { key: 2, seq: 2 },
        Item { key: 1, seq: 3 },
        Item { key: 3, seq: 4 },
        Item { key: 2, seq: 5 },
        Item { key: 1, seq: 6 },
        Item { key: 3, seq: 7 },
        Item { key: 2, seq: 8 },
        Item { key: 1, seq: 9 },
        Item { key: 3, seq: 10 },
        Item { key: 2, seq: 11 },
        Item { key: 1, seq: 12 },
        Item { key: 3, seq: 13 },
        Item { key: 2, seq: 14 },
        Item { key: 1, seq: 15 },
        Item { key: 3, seq: 16 },
        Item { key: 2, seq: 17 }
    }
    sort.by[Item](items, less_item)
    io.println(items[0].key)
    io.println(items[5].key)
    io.println(items[11].key)
    io.println(items[17].key)
    io.println(sort.is_sorted_by[Item](items, less_item))
}

# STDOUT: 0
# STDOUT: 7
# STDOUT: 1
# STDOUT: 16
# STDOUT: 32
# STDOUT: 1
# STDOUT: 1
# STDOUT: 1
# STDOUT: 2
# STDOUT: 3
# STDOUT: 1
