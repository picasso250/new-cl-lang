extern "c" {
    fun putchar(c: i32): i32
}

# STDOUT: A

fun main() {
    let ignored = putchar(65)
}
