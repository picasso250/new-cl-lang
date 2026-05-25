import io
fun f(x: f64) {
  io.println(x)
}

fun main() {
  f(1.0f32)
}

# ERROR: argument x to f: expected f64, got f32
