# ERROR: err? handler: expected i32, got str

fun fail(): i32 {
    err "bad"
}

fun main() {
    let x = fail() err? e {
        "bad"
    }
}
