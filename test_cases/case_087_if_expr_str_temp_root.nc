import io
# STDOUT: ab
fun main() {
    let s = "a" + if true { "b" } else { "c" }
    io.println(s)
}
