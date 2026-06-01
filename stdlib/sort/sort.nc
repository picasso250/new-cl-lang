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
            return false
        }
    }
    return true
}
