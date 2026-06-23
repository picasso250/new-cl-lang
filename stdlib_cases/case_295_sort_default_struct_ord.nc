import io
import sort
# STDOUT: 1
# STDOUT: 2
# STDOUT: 3

struct Item { key: i32 }

fun (i *Item) __lt__(other: Item): bool {
    i.key < other.key
}

fun main() {
    let xs = []Item {
        Item { key: 3 },
        Item { key: 1 },
        Item { key: 2 }
    }
    sort.sort[Item](xs)
    io.println(xs[0].key)
    io.println(xs[1].key)
    io.println(xs[2].key)
}
