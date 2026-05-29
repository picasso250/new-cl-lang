import io

struct Box[T] { value: T }

fun main() {
  let a = Box[str] { value: "ok" }
  let b = new Box[i32] { value: 7 }
  io.println(a.value)
  io.println(b.value)
}

# STDOUT: ok
# STDOUT: 7
