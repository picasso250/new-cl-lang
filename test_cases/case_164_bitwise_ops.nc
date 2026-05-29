import io
fun main() {
  let a: i32 = 6
  let b: i32 = 3
  io.println(a & b)
  io.println(a | b)
  io.println(a ^ b)
  io.println(~0)
  io.println(1 + 2 << 3 & 31)
  io.println(1 | 2 + 4 ^ 8)
  let u: u32 = 16u32
  io.println(u >> 2u32)
}

# STDOUT: 2
# STDOUT: 7
# STDOUT: 5
# STDOUT: -1
# STDOUT: 17
# STDOUT: 15
# STDOUT: 4
