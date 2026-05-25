import io
# ERROR: match expression: non-enum match requires else
fun main() {
    let n = 1
    let result = match n {
        1 -> 10
    }
    io.println(result)
}
