import io
import sort

struct Item { key: i32, name: str }

fun main() {
    let less_i32 = fun(a: i32, b: i32): bool { a < b }
    let xs = []i32 { 4, 1, 3, 2 }
    sort.by[i32](xs, less_i32)
    io.println(xs[0])
    io.println(xs[1])
    io.println(xs[2])
    io.println(xs[3])
    io.println(sort.is_sorted_by[i32](xs, less_i32))

    let items = []Item {
        Item { key: 2, name: "b" },
        Item { key: 1, name: "a" }
    }
    let less_item = fun(a: Item, b: Item): bool { a.key < b.key }
    sort.by[Item](items, less_item)
    io.println(items[0].name)
    io.println(items[1].name)
}

# STDOUT: 1
# STDOUT: 2
# STDOUT: 3
# STDOUT: 4
# STDOUT: 1
# STDOUT: a
# STDOUT: b
