import io

fun fail(): i32 {
    err "bad"
}

fun choose(flag: bool): i32 {
    if flag {
        10
    } else {
        err "no"
    }
}

fun classify(x: i32): i32 {
    match x {
        0 -> err "zero"
        1 -> ret 11
        else -> 12
    }
}

fun main() {
    io.println(choose(true)!!)
    io.println(classify(2)!!)
}

# STDOUT: 10
# STDOUT: 12
