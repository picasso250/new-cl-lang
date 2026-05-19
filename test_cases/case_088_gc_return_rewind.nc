# STDOUT: 0

fun helper(): i32 {
    let s = str(1)
    s = str(2)
    return 7
}

fun main() {
    helper()
    gc_collect()
    gc_live()
}
