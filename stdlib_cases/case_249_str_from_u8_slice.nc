import io

# STDOUT: ABC
# STDOUT: Z
# STDOUT: ABC
fun main() {
    let bytes = []u8 { 65u8, 66u8, 67u8 }
    let text = str(bytes)
    io.println(text)
    bytes[0] = 90u8
    io.println(str([]u8 { bytes[0] }))
    io.println(text)
}
