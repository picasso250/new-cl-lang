import io
# ERROR: match expression arms: expected i32, got str
fun main() {
    let n = 1
    let result = match n {
        1 -> 10
        else -> "many"
    }
    io.println(result)
}
