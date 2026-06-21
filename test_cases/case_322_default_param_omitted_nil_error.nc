# ERROR: default parameter p: cannot infer type from __nil

fun bad(p = nil): i32 {
    0
}

fun main() {
    bad()
}
