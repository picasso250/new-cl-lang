import io

type IntFun = (i32) -> i32

fun apply(f: IntFun, x: i32): i32 {
  f(x)
}

fun main() {
  let f: IntFun = fun(x: i32): i32 { x * 2 }
  io.println(apply(f, 21))
}

# STDOUT: 42
