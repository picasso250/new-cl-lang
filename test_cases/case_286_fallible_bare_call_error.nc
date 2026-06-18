# ERROR: fallible call fail must be handled with ??, !!, or is err

fun fail() {
    err "bad"
}

fun main() {
    fail()
}
