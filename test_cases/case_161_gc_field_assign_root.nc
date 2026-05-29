import runtime
import io
# STDOUT: 42

struct Box { s: str }

fun main() {
    let b = Box { s: "" }
    b.s = str(42)
    runtime.gc_collect()
    io.println(b.s)
}
