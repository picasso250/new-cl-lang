import runtime
import io
# STDOUT: 42

fun main() {
    let xs = [1]str { "" }
    xs[0] = str(42)
    runtime.gc_collect()
    io.println(xs[0])
}
