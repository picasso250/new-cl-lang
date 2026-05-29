fun id[T](x: T): T { x }

fun main() {
  let x = id(1)
}

# ERROR: generic function id requires explicit type args
