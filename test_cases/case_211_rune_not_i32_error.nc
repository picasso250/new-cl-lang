# ERROR: let x: expected i32, got rune
import io
fun main() {
    let x: i32 = 'A'
    io.println(x)
}
