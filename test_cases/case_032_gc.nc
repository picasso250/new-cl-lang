import io
# STDOUT: before gc: alive
# STDOUT: after gc: alive

fun main() {
    let s = "alive"
    io.println("before gc: " + s)
    gc_collect()
    io.println("after gc: " + s)
}
