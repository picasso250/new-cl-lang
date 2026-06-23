# ERROR: fallible call fail must be handled with ??, !!, or try

fun fail() {
    err "bad"
}

fun main() {
    fail()
}
