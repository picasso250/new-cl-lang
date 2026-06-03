import io
import sort

fun main() {
    let xs = []i32 { 4, 1, 3, 2 }
    sort.sort[i32](xs)
    for i, x in xs {
        io.println(x)
    }
}

# STDOUT: 1
# STDOUT: 2
# STDOUT: 3
# STDOUT: 4
