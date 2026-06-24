# ERROR: let x: cannot bind never value

fun main() {
    let x = if true {
        err "a"
    } else {
        err "b"
    }
}
