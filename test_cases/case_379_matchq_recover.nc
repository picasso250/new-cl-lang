import io

fun code(kind: i32): i32 {
    if kind == 1 {
        err "not found"
    }
    if kind == 2 {
        err "denied"
    }
    9
}

fun handle(kind: i32): i32 {
    code(kind) match? e {
        "not found" -> 3
        "empty" -> 4
        else -> err e
    }
}

fun main() {
    io.println(handle(0)!!)
    io.println(handle(1)!!)
}

# STDOUT: 9
# STDOUT: 3
