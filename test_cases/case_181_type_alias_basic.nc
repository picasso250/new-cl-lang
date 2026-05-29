import io

type ID = u64
type Name = str

fun main() {
  let x: ID = 42u64
  let y: Name = "hello"
  io.println(x)
  io.println(y)
}

# STDOUT: 42
# STDOUT: hello
