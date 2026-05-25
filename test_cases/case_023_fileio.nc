import io
# STDOUT: hello
fun main() {
    write_file("__test.txt", "hello")
    let content = read_file("__test.txt")
    io.println(content)
}
