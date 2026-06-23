import io

# STDOUT: 12

fun fail(kind: i32): i32 {
    if kind == 1 {
        err "not found"
    }
    err "denied"
}

fun classify(kind: i32): i32 {
    let result = 0
    try value = fail(kind) {
        result = value
    } else e {
        result = match e {
            "not found" -> 10
            "timeout" -> 11
            else -> 12
        }
    }
    ret result
}

fun main() {
    io.println(classify(2))
}
