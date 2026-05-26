import io
# STDOUT: 42

fun use(s: str) {
    gc_collect()
    io.println(s)
}

fun main() {
    use(str(42))
}
