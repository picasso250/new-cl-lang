import io

struct Point { x: f64, y: f64 }

type Ptr = *Point

fun main() {
  let p = new Point { x: 3.0, y: 4.0 }
  let q: Ptr = p
  io.println(q.x)
}

# STDOUT: 3
