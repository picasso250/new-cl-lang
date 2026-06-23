# ERROR: Variable 'value' not found

fun ok(): i32 {
    if false {
        err "bad"
    }
    ret 7
}

fun main() {
    try value = ok() {
    } else e {
    }
    let x = value
}
