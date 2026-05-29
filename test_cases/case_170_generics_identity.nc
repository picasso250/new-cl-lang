import io

fun id[T](x: T): T { x }

fun main() {
  io.println(id[i32](42))
  io.println(id[str]("ok"))
  io.println(id[bool](true))
}

# STDOUT: 42
# STDOUT: ok
# STDOUT: 1
