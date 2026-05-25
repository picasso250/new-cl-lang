import io
# ERROR: argument 1 to f: expected i32, got str
fun main() {
    let f = fun(x: i32): i32 { x }
    io.println(f("bad"))
}
