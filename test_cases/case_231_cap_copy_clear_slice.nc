# STDOUT: 2
# STDOUT: 2
# STDOUT: 3
# STDOUT: 4
# STDOUT: 0
# STDOUT: 0
import io

fun main() {
    let xs = []i32 { 1, 2, 3, 4 }
    let dst = xs[0:2]
    io.println(cap(dst))
    io.println(copy(dst, xs[2:4]))
    io.println(dst[0])
    io.println(dst[1])
    clear(dst)
    io.println(dst[0])
    io.println(dst[1])
}
