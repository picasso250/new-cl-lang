# STDOUT: 9
# RC: 7
fun main(): i32 {
    defer {
        print(9)
    }
    return 7
}
