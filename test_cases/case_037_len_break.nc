# STDOUT: 5
# STDOUT: 0
# STDOUT: 1
# STDOUT: 2

fun main() {
    let s = "hello"
    print(len(s))
    let x = 10
    for i in 0..x {
        if i == 3 {
            break
        }
        print(i)
    }
}
