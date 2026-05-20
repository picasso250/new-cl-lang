# STDOUT: 20
fun make(): () -> i32 {
    let xs = []i32 { 10, 20, 30 }
    fun(): i32 { xs[1] }
}

fun main() {
    let f = make()
    print(f())
}
