# ERROR: assignment: expected i32, got str
fun main() {
    let mut x: i32 = 1
    x = "bad"
    print(x)
}
