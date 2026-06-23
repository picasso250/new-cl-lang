# ERROR: try: void fallible call cannot bind a success value

fun fail() {
    err "bad"
}

fun main() {
    try value = fail() {
    } else e {
    }
}
