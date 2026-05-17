# ERROR: if expression branches: expected i32, got str
fun main() {
    let x = if true { 1 } else { "bad" }
    print(x)
}
