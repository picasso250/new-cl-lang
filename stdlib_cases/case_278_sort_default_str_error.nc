# ERROR: generic function sort.sort: type arg str does not satisfy types.Cmp

import sort

fun main() {
    let xs = []str { "b", "a" }
    sort.sort[str](xs)
}
