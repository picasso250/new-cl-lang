import runtime
import io
# STDOUT: 42

fun use(s: str) {
    runtime.gc_collect()
    io.println(s)
}

fun main() {
    use(str(42))
}
