import runtime
import io
# STDOUT: ok

fun helper() {
    let s = str(42)
    # s._ptr 在 GC 登记表里，helper 返回时 pop_root
}

fun main() {
    helper()
    runtime.gc_collect()
    io.println("ok")
}
