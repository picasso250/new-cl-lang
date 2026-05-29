import runtime
import io
# STDOUT: 1

fun main() {
    let xs = []i32 { 1 }
    xs = append(xs, 2)
    runtime.gc_collect()
    io.println(xs[0])
}
