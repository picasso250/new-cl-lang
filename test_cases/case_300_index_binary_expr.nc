import io

fun main() {
    let xs = []i32 { 10, 20, 30, 40 }
    let j = 2
    let lo = 1
    let root = 1
    io.println(xs[j - 1])
    io.println(xs[lo + root])
    io.println(len(xs[1: j + 1]))
}

# STDOUT: 20
# STDOUT: 30
# STDOUT: 2
