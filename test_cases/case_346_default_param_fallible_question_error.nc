# ERROR: default parameter x: fallible operations are not allowed

fun fail(): i32 {
    err "bad"
}

fun bad(x: i32 = fail()??): i32 {
    x
}

fun main() {
    bad()
}
