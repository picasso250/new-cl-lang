# ERROR: match? pattern: expected str literal, got i32

fun fail(): i32 {
    err "bad"
}

fun main() {
    let x = fail() match? e {
        1 -> 1
        else -> 2
    }
}
