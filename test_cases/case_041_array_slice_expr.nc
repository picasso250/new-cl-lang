# STDOUT: 2
# STDOUT: 60
fun main() {
    let arr = [4]i32 { 10, 20, 30, 40 }
    print(len(arr[1:3]))
    let s = arr[1:4]
    print(s[0] + s[2])
}
