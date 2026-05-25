import io
# STDOUT: 3
# STDOUT: 60
fun main() {
    let s = []i32 { 10, 20, 30 }
    io.println(len(s))
    io.println(s[0] + s[1] + s[2])
}
