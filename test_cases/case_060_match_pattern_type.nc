# ERROR: match pattern: expected i32, got bool
fun main() {
    let x = 1
    let result = match x {
        true -> 1
        else -> 2
    }
    print(result)
}
