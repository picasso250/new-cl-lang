import io
# ERROR: let x: expected i32, got str
fun main() {
    let x: i32 = "bad"
    io.println(x)
}
