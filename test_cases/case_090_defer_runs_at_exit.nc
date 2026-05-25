import io
# STDOUT: 2
# STDOUT: 1
fun main() {
    defer {
        io.println(1)
    }
    io.println(2)
}
