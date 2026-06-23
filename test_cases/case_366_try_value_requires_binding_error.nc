# ERROR: try: fallible call returning i32 requires a success binding

fun fail(): i32 {
    err "bad"
}

fun main() {
    try fail() {
    } else e {
    }
}
