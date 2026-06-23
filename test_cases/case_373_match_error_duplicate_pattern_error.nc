# ERROR: match expression: duplicate pattern

fun fail() {
    err "bad"
}

fun main() {
    try fail() {
    } else e {
        let label = match e {
            "bad" -> 1
            "bad" -> 2
            else -> 3
        }
    }
}
