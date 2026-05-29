fun id[T](x: T): T { x }

fun main() {
  let x: str = id[i32](1)
}

# ERROR: let x: expected str, got i32
