import runtime

# STDOUT: 1

fun main() {
    let s = str(42)
    runtime.gc_collect()
    runtime.gc_live()
}
