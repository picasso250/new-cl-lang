import io
# ERROR: if expression branches: expected i32, got void
fun main() {
    let x = if true { 1 }
    io.println(x)
}
