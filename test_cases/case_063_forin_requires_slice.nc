import io
# ERROR: for-in: expected slice, got str
fun main() {
    let s = "abc"
    for i, ch in s {
        io.println(ch)
    }
}
