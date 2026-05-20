# STDOUT: hello
fun make(): () -> str {
    let s = "hello"
    fun(): str { s }
}

fun main() {
    let f = make()
    print(f())
}
