# STDOUT: 8
fun add1(x: i32): i32 {
    x + 1
}

fun main() {
    print(add1({
        let a = 7
        a
    }))
}
