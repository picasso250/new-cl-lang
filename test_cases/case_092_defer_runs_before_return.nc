import io
# STDOUT: 9
# RC: 7
fun main(): i32 {
    defer {
        io.println(9)
    }
    ret 7
}
