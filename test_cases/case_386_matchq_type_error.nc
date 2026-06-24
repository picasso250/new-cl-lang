# ERROR: match? arms: expected i32, got str

fun fail(): i32 {
    err "bad"
}

fun main() {
    let x = fail() match? e {
        "bad" -> "bad"
        else -> 3
    }
}
