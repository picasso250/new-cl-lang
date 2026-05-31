# ERROR: copy src: expected []i32, got []str
fun main() {
    let xs = []i32 { 1 }
    let ys = []str { "x" }
    copy(xs, ys)
}
