# ERROR: cannot assign to captured variable 'base'
fun main() {
    let base = 10
    let f = fun(): i32 {
        base = 2
        base
    }
    print(f())
}
