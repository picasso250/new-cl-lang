import io
# ERROR: for range start: expected i32, got bool
fun main() {
    for i in true..3 {
        io.println(i)
    }
}
