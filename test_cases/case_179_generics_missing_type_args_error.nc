struct Box[T] { value: T }

fun main() {
  let b: Box = Box[i32] { value: 1 }
}

# ERROR: generic type Box requires explicit type args
