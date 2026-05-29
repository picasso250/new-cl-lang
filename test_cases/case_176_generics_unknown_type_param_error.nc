fun bad[T](x: U): U { x }

fun main() {
  let x = bad[i32](1)
}

# ERROR: argument x to bad__i32: expected U, got i32
