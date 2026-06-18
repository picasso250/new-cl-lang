import fs
import io
# STDOUT: hello
fun main() {
    fs.write_file("__test.txt", "hello")!!
    let content = fs.read_file("__test.txt")!!
    io.println(content)
}
