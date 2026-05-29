struct Point { x: i32 }

fun main() {
  let p = Point[i32] { x: 1 }
}

# ERROR: type Point is not generic
