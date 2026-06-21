# ERROR: default parameter x: cannot infer type from void

fun noop() {
}

fun bad(x = noop()): i32 {
    0
}

fun main() {
    bad()
}
