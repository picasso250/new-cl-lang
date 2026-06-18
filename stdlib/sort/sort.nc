import types

fun sort[T types.Ord](items: []T) {
    for i in 1..len(items) {
        let value = items[i]
        let j = i
        for j > 0 {
            let prev = items[j - 1]
            if !(value < prev) {
                break
            }
            items[j] = prev
            j = j - 1
        }
        items[j] = value
    }
}

fun by[T](items: []T, less: fun(T, T) bool) {
    for i in 1..len(items) {
        let value = items[i]
        let j = i
        for j > 0 && less(value, items[j - 1]) {
            items[j] = items[j - 1]
            j = j - 1
        }
        items[j] = value
    }
}

fun is_sorted_by[T](items: []T, less: fun(T, T) bool): bool {
    for i in 1..len(items) {
        if less(items[i], items[i - 1]) {
            ret false
        }
    }
    ret true
}
