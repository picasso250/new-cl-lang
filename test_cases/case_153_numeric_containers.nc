import io
struct Box { value: u64 }

fun main() {
  let b = Box { value: 9u64 }
  let arr: [2]u8 = [2]u8 { 4u8, 5u8 }
  let sl: []f32 = []f32 { 1.25f32, 2.5f32 }
  io.println(b.value)
  io.println(arr[1])
  io.println(sl[0])
}

# STDOUT: 9
# STDOUT: 5
# STDOUT: 1.25
