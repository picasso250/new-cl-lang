import io
# STDOUT: 42
# STDOUT: hello99

fun main() {
    let s = str(42)
    io.println(s)
    let result = "hello" + str(99)
    io.println(result)
}
