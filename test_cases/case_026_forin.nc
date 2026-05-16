# STDOUT: 10
# STDOUT: 20
# STDOUT: 30
fun main() {
    let arr = [3]i32 { 10, 20, 30 }
    let s = arr[0:3]
    for i, item in s {
        print(item)
    }
}
