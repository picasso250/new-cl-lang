# ERROR: Variable 'e' not found

fun fail() {
    err "bad"
}

fun main() {
    try fail() {
    } else e {
    }
    let x = e
}
