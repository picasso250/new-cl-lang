import io
# STDOUT: hello
fun make(): fun() str {
    let s = "hello"
    fun(): str { s }
}

fun main() {
    let f = make()
    io.println(f())
}
