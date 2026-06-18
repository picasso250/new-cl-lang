# STDERR: error: boom
# RC: 1

fun fail(): i32 {
    err "boom"
}

fun main() {
    fail()!!
}
