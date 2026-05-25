import io
# ERROR: if condition: expected bool, got i32
fun main() {
    if 1 {
        io.println("bad")
    }
}
