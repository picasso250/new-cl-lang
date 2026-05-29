import io

struct Box[T] { value: T }

fun main() {
  let b = Box[Box[i32]] { value: Box[i32] { value: 5 } }
  io.println(b.value.value)
}

# STDOUT: 5
