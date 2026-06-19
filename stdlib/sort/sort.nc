import types

fun sort[T types.Ord](items: []T): void {
    let n = len(items)
    if n < 2 {
        ret
    }
    _sort_intro_ord[T](items, 0, n, _sort_depth_limit(n))
    _sort_insertion_ord[T](items, 0, n)
}

fun by[T](items: []T, less: fun(T, T) bool): void {
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

fun _sort_depth_limit(n: i32): i32 {
    let depth = 0
    for n > 1 {
        n = n / 2
        depth = depth + 1
    }
    ret depth * 2
}

fun _sort_intro_ord[T types.Ord](items: []T, lo: i32, hi: i32, depth: i32): void {
    let threshold = 16
    for hi - lo > threshold {
        if depth == 0 {
            _sort_heap_ord[T](items, lo, hi)
            ret
        }

        depth = depth - 1
        let pivot = _sort_partition_ord[T](items, lo, hi)

        if pivot - lo < hi - (pivot + 1) {
            _sort_intro_ord[T](items, lo, pivot, depth)
            lo = pivot + 1
        } else {
            _sort_intro_ord[T](items, pivot + 1, hi, depth)
            hi = pivot
        }
    }
}

fun _sort_partition_ord[T types.Ord](items: []T, lo: i32, hi: i32): i32 {
    let mid = lo + (hi - lo) / 2
    let last = hi - 1

    let mid_value_1 = items[mid]
    let lo_value_1 = items[lo]
    if mid_value_1 < lo_value_1 {
        _sort_swap[T](items, lo, mid)
    }
    let last_value = items[last]
    let mid_value_2 = items[mid]
    if last_value < mid_value_2 {
        _sort_swap[T](items, mid, last)
    }
    let mid_value_3 = items[mid]
    let lo_value_2 = items[lo]
    if mid_value_3 < lo_value_2 {
        _sort_swap[T](items, lo, mid)
    }

    let pivot_value = items[mid]
    _sort_swap[T](items, mid, last)

    let store = lo
    for i in lo..last {
        let item = items[i]
        if item < pivot_value {
            _sort_swap[T](items, i, store)
            store = store + 1
        }
    }

    _sort_swap[T](items, store, last)
    ret store
}

fun _sort_insertion_ord[T types.Ord](items: []T, lo: i32, hi: i32): void {
    for i in lo + 1..hi {
        let value = items[i]
        let j = i
        for j > lo {
            let prev = j - 1
            if !(value < items[prev]) {
                break
            }
            items[j] = items[prev]
            j = j - 1
        }
        items[j] = value
    }
}

fun _sort_heap_ord[T types.Ord](items: []T, lo: i32, hi: i32): void {
    let count = hi - lo

    let start = count / 2
    for start > 0 {
        start = start - 1
        _sort_sift_down_ord[T](items, lo, start, count)
    }

    let end = count
    for end > 1 {
        end = end - 1
        _sort_swap[T](items, lo, lo + end)
        _sort_sift_down_ord[T](items, lo, 0, end)
    }
}

fun _sort_sift_down_ord[T types.Ord](items: []T, lo: i32, root: i32, count: i32): void {
    for true {
        let child = root * 2 + 1
        if child >= count {
            ret
        }

        let largest = root
        let largest_index = lo + largest
        let child_index = lo + child
        let largest_value = items[largest_index]
        let child_value = items[child_index]
        if largest_value < child_value {
            largest = child
        }

        let right = child + 1
        if right < count {
            let current_index = lo + largest
            let right_index = lo + right
            let current_value = items[current_index]
            let right_value = items[right_index]
            if current_value < right_value {
                largest = right
            }
        }

        if largest == root {
            ret
        }

        _sort_swap[T](items, lo + root, lo + largest)
        root = largest
    }
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
            let prev = j - 1
            if !less(value, items[prev]) {
                break
            }
            items[j] = items[prev]
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
        let largest_index = lo + largest
        let child_index = lo + child
        let largest_value = items[largest_index]
        let child_value = items[child_index]
        if less(largest_value, child_value) {
            largest = child
        }

        let right = child + 1
        if right < count {
            let current_index = lo + largest
            let right_index = lo + right
            let current_value = items[current_index]
            let right_value = items[right_index]
            if less(current_value, right_value) {
                largest = right
            }
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
