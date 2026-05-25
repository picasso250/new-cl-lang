import io
# ERROR: 4:5: let x: expected i32, got str
fun main() {
    let x: i32 = "bad"
    io.println(x)
}
