# ERROR: try requires a fallible call

fun ok(): i32 {
    ret 1
}

fun main() {
    try value = ok() {
    }
}
