import fs
import io

# STDOUT: 3
# STDOUT: 65
# STDOUT: ABC
fun main() {
    fs.write_file("__test_bytes.txt", "ABC")!!
    let bytes = fs.read_bytes("__test_bytes.txt")!!
    io.println(len(bytes))
    io.println(i32(bytes[0]))
    io.println(str(bytes))
    fs.remove("__test_bytes.txt")!!
}
