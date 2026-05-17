# ERROR: array literal: expected 3 elements, got 2
fun main() {
    let xs = [3]i32 { 1, 2 }
    print(xs[0])
}
