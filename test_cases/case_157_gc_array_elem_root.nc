import runtime
import io
# STDOUT: 42

fun main() {
    let xs = [2]str { str(42), str(7) }
    runtime.gc_collect()
    io.println(xs[0])
}
