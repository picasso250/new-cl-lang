# STDOUT: before gc: alive
# STDOUT: after gc: alive

fun main() {
    let s = "alive"
    print("before gc: " + s)
    gc_collect()
    print("after gc: " + s)
}
