import io
# ERROR: invalid assignment target
fun main() {
  let x = 1
  x + 1++
  io.println(x)
}
