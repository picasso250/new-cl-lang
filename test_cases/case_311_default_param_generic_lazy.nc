import io

# STDOUT: 1
# STDOUT: 1

struct Item { key: i32 }

fun less_default[T any](a: T, b: T): bool {
    a < b
}

fun less_item(a: Item, b: Item): bool {
    a.key < b.key
}

fun before[T any](a: T, b: T, less: fun(T, T) bool = less_default[T]): bool {
    less(a, b)
}

fun main() {
    io.println(before[i32](1, 2))
    io.println(before[Item](Item { key: 1 }, Item { key: 2 }, less_item))
}
