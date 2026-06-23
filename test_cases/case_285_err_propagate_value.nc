import io

# STDOUT: bad

fun leaf(): i32 {
    err "bad"
}

fun wrap(): i32 {
    ret leaf()??
}

fun main() {
    try value = wrap() {
        io.println(value)
    } else e {
        io.println("bad")
    }
}
