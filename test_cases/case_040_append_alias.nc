import io
# STDOUT: 30
# STDOUT: 40
# STDOUT: 99
# STDOUT: 40
fun main() {
    let arr = []i32 { 10, 20, 30, 40 }
    let s1 = arr[1:3]
    s1[1] = 99
    io.println(arr[2])
    io.println(arr[3])
    let s2 = append(s1, 77)
    io.println(s2[1])
    io.println(arr[3])
}
