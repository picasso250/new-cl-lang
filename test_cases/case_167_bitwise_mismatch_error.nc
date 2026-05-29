import io
# ERROR: binary operator |: expected i32, got i64
fun main() {
  let x = 1 | 2i64
  io.println(x)
}
