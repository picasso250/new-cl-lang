# ERROR: defer cannot propagate fallible calls with ??

fun fail() {
    err "bad"
}

fun main() {
    defer {
        fail()??
    }
}
