# ERROR: fallible call fail must be handled with ??, !!, or is err

fun fail(): i32 {
    err "bad"
}

fun outer(x: i32): i32 {
    err "outer"
}

fun main() {
    outer(fail())??
}
