import io

type ID = u64
type ID = str

fun main() {
  let x: ID = "bad"
  io.println(x)
}

# ERROR: duplicate type alias
