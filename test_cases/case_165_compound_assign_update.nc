import io
struct Box { value: i32 }
fun main() {
  let x: i32 = 5
  x += 3
  x *= 2
  x--
  io.println(x)
  let b = Box { value: 1 }
  b.value += 4
  io.println(b.value)
  let a = [3]i32 { 1, 2, 3 }
  a[1] <<= 2
  io.println(a[1])
  let f: f64 = 1.5
  f++
  io.println(f)
  let s = map_new()
  s["a"] = "x"
  s["a"] += "y"
  io.println(s["a"])
}

# STDOUT: 15
# STDOUT: 5
# STDOUT: 8
# STDOUT: 2.5
# STDOUT: xy
