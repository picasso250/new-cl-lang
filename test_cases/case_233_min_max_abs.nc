# STDOUT: -2
# STDOUT: 7
# STDOUT: 9
# STDOUT: 1.5
# STDOUT: 4.25
# STDOUT: 8
import io

fun main() {
    io.println(min(-2, 7))
    io.println(max(-2, 7))
    io.println(abs(-9))
    io.println(min(1.5, 2.5))
    io.println(abs(-4.25))
    io.println(max(3u32, 8u32))
}
