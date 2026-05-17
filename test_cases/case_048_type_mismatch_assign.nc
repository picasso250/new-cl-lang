# ERROR: assignment: expected i32, got str
fun main() {
    let x: i32 = 1
    x = "bad"
    print(x)
}
