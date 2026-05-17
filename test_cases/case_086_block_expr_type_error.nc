# ERROR: let x: expected i32, got str
fun main() {
    let x: i32 = {
        "bad"
    }
    print(x)
}
