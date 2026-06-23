# ERROR: match expression: error match requires else

fun fail() {
    err "bad"
}

fun main() {
    try fail() {
    } else e {
        let label = match e {
            "bad" -> 1
        }
    }
}
