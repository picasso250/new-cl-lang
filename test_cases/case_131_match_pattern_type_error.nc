# ERROR: match pattern: expected i32, got str
fun main() {
    let n = 1
    let result = match n {
        "one" -> 1
        else -> 2
    }
    print(result)
}
