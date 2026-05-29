import runtime
import io
# STDOUT: before gc: alive
# STDOUT: after gc: alive

fun main() {
    let s = "alive"
    io.println("before gc: " + s)
    runtime.gc_collect()
    io.println("after gc: " + s)
}
