# ERROR: match? expression requires else

fun fail(): i32 {
    err "bad"
}

fun main() {
    let x = fail() match? e {
        "bad" -> 1
    }
}
