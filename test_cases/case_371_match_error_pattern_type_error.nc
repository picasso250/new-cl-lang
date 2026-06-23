# ERROR: match error pattern: expected str literal, got i32

fun fail() {
    err "bad"
}

fun main() {
    try fail() {
    } else e {
        let label = match e {
            1 -> 1
            else -> 2
        }
    }
}
