import io
# STDOUT: 60
fun main() {
    let arr = [3]i32 { 10, 20, 30 }
    let s = arr[0:3]
    io.println(s[0] + s[1] + s[2])
}
