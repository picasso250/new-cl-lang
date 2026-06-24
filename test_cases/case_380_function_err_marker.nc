import io

fun fail(): i32 err {
    err "marked"
}

fun main() {
    let v = fail() err? e {
        42
    }
    io.println(v)
}

# STDOUT: 42
