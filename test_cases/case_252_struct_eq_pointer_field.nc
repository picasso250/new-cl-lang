import io
# STDOUT: 1
# STDOUT: 0
struct Cell { value: i32 }
struct Holder { cell: *Cell }

fun main() {
    let cell = new Cell { value: 3 }
    let other = new Cell { value: 3 }
    let a = Holder { cell: cell }
    let b = Holder { cell: cell }
    let c = Holder { cell: other }
    io.println(a == b)
    io.println(a == c)
}
