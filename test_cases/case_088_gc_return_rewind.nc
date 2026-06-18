import runtime
# STDOUT: 0

fun helper(): i32 {
    let s = str(1)
    s = str(2)
    ret 7
}

fun main() {
    helper()
    runtime.gc_collect()
    runtime.gc_live()
}
