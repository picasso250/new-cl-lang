import io
import runtime
# STDOUT: 12345

struct Box { s: str }

fun main() {
    let m = map[str,Box]()
    m["x"] = Box { s: str(12345) }
    runtime.gc_collect()
    let b = m["x"]
    io.println(b.s)
}
