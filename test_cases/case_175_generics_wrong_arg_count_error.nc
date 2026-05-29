fun id[T](x: T): T { x }

fun main() {
  let x = id[i32, str](1)
}

# ERROR: generic function id: expected 1 type args, got 2
