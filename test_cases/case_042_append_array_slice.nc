import io
# STDOUT: 99
# STDOUT: 40
fun main() {
    let arr = [4]i32 { 10, 20, 30, 40 }
    let s = append(arr[1:3], 99)
    io.println(s[2])
    io.println(arr[3])
}
