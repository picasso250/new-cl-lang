import io

# ERROR: Unexpected token

fun f(x: i32): i32 {
    x
}

fun main() {
    io.println(f(1,,))
}
