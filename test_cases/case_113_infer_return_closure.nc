# STDOUT: hello

fun make() {
    let s = "hello"
    fun() { s }
}

fun main() {
    let f = make()
    print(f())
}
