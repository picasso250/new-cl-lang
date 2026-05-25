import io
# ERROR: match expression: duplicate pattern
fun main() {
    let n = 1
    let result = match n {
        1 -> 10
        1 -> 20
        else -> 30
    }
    io.println(result)
}
