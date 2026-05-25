import io
# STDOUT: 2
fun main() {
    if false {
        defer {
            io.println(1)
        }
    }
    defer {
        io.println(2)
    }
}
