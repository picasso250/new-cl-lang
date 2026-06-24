# ERROR: match? expression: duplicate pattern

fun fail(): i32 {
    err "bad"
}

fun main() {
    let x = fail() match? e {
        "bad" -> 1
        "bad" -> 2
        else -> 3
    }
}
