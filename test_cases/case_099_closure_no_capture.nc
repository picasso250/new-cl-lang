import io
# STDOUT: 6
fun main() {
    let inc = fun(x: i32): i32 { x + 1 }
    io.println(inc(5))
}
