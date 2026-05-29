import io

struct Cell { value: i32 }
struct Bag[T] { items: []T, first: *Cell, backup: *Cell }

fun main() {
  let c = new Cell { value: 9 }
  let items = []i32 { 1, 2 }
  let b = Bag[i32] { items: items, first: c, backup: c }
  io.println(b.items[1])
  io.println(b.first.value)
  io.println(b.backup.value)
}

# STDOUT: 2
# STDOUT: 9
# STDOUT: 9
