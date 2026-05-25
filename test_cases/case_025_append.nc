import io
# STDOUT: 60
fun main() {
    let arr = [3]i32 { 10, 0, 0 }
    let s = arr[0:1]
    s = append(s, 20)
    s = append(s, 30)
    io.println(s[0] + s[1] + s[2])
}
