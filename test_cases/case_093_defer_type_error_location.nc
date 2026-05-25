import io
# ERROR: 5:9: io.println: expected 1 args, got 2
fun main() {
    defer {
        io.println(1, 2)
    }
}
