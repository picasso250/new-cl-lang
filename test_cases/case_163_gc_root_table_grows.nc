import runtime
import io
# STDOUT: ok

fun main() {
    let i = 0
    for i < 5000 {
        let s = str(i)
        i = i + 1
    }
    runtime.gc_collect()
    io.println("ok")
}
