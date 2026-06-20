fun sort[T any](items: []T, less: fun(T, T) bool = _sort_less_default[T]): void {
    let n = len(items)
    if n < 2 {
        ret
    }
    _sort_intro_by[T](items, 0, n, _sort_depth_limit(n), less)
    _sort_insertion_by[T](items, 0, n, less)
}

fun is_sorted_by[T](items: []T, less: fun(T, T) bool): bool {
    for i in 1..len(items) {
        if less(items[i], items[i - 1]) {
            ret false
        }
    }
    ret true
}

fun _sort_less_default[T any](a: T, b: T): bool {
    a < b
}

fun _sort_depth_limit(n: i32): i32 {
    let depth = 0
    for n > 1 {
        n = n / 2
        depth = depth + 1
    }
    ret depth * 2
}

fun _sort_intro_by[T](items: []T, lo: i32, hi: i32, depth: i32, less: fun(T, T) bool): void {
    let threshold = 16
    for hi - lo > threshold {
        if depth == 0 {
            _sort_heap_by[T](items, lo, hi, less)
            ret
        }

        depth = depth - 1
        let pivot = _sort_partition_by[T](items, lo, hi, less)

        if pivot - lo < hi - (pivot + 1) {
            _sort_intro_by[T](items, lo, pivot, depth, less)
            lo = pivot + 1
        } else {
            _sort_intro_by[T](items, pivot + 1, hi, depth, less)
            hi = pivot
        }
    }
}

fun _sort_partition_by[T](items: []T, lo: i32, hi: i32, less: fun(T, T) bool): i32 {
    let mid = lo + (hi - lo) / 2
    let last = hi - 1

    if less(items[mid], items[lo]) {
        _sort_swap[T](items, lo, mid)
    }
    if less(items[last], items[mid]) {
        _sort_swap[T](items, mid, last)
    }
    if less(items[mid], items[lo]) {
        _sort_swap[T](items, lo, mid)
    }

    let pivot_value = items[mid]
    _sort_swap[T](items, mid, last)

    let store = lo
    for i in lo..last {
        if less(items[i], pivot_value) {
            _sort_swap[T](items, i, store)
            store = store + 1
        }
    }

    _sort_swap[T](items, store, last)
    ret store
}

fun _sort_insertion_by[T](items: []T, lo: i32, hi: i32, less: fun(T, T) bool): void {
    for i in lo + 1..hi {
        let value = items[i]
        let j = i
        for j > lo {
            if !less(value, items[j - 1]) {
                break
            }
            items[j] = items[j - 1]
            j = j - 1
        }
        items[j] = value
    }
}

fun _sort_heap_by[T](items: []T, lo: i32, hi: i32, less: fun(T, T) bool): void {
    let count = hi - lo

    let start = count / 2
    for start > 0 {
        start = start - 1
        _sort_sift_down_by[T](items, lo, start, count, less)
    }

    let end = count
    for end > 1 {
        end = end - 1
        _sort_swap[T](items, lo, lo + end)
        _sort_sift_down_by[T](items, lo, 0, end, less)
    }
}

fun _sort_sift_down_by[T](items: []T, lo: i32, root: i32, count: i32, less: fun(T, T) bool): void {
    for true {
        let child = root * 2 + 1
        if child >= count {
            ret
        }

        let largest = root
        if less(items[lo + largest], items[lo + child]) {
            largest = child
        }

        let right = child + 1
        if right < count && less(items[lo + largest], items[lo + right]) {
            largest = right
        }

        if largest == root {
            ret
        }

        _sort_swap[T](items, lo + root, lo + largest)
        root = largest
    }
}

fun _sort_swap[T](items: []T, a: i32, b: i32): void {
    if a == b {
        ret
    }
    let tmp = items[a]
    items[a] = items[b]
    items[b] = tmp
}
