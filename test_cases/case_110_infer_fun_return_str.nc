import io
# STDOUT: hello

fun greet() {
    ret "hello"
}

fun main() {
    io.println(greet())
}
