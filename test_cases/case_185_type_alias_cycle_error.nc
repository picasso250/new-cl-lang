import io

type A = B
type B = A

fun main() {
  let x: A = 42
  io.println(x)
}

# ERROR: type alias cycle
