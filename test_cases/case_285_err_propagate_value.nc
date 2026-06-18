import io

# STDOUT: bad

fun leaf(): i32 {
    err "bad"
}

fun wrap(): i32 {
    ret leaf()??
}

fun main() {
    if wrap() is err {
        io.println("bad")
    }
}
