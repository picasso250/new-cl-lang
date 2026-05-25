import io
# STDOUT: 3
# STDOUT: 2
# STDOUT: 1
fun main() {
    defer {
        io.println(1)
    }
    defer {
        io.println(2)
    }
    io.println(3)
}
