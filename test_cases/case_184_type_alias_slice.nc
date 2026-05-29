import io

type Ints = []i32

fun sum(xs: Ints): i32 {
  let s: i32 = 0
  for i, v in xs {
    s += v
  }
  s
}

fun main() {
  let xs: Ints = []i32 { 1, 2, 3 }
  io.println(sum(xs))
}

# STDOUT: 6
