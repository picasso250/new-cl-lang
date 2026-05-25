import io
# STDOUT: 3
# STDOUT: 3
fun main() {
    let i = 0
    for i < 2 {
        defer {
            io.println(3)
        }
        i = i + 1
    }
}
