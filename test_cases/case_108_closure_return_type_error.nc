import io
# ERROR: ret: expected fun(i32) i32, got fun(i32) str
fun bad(): fun(i32) i32 {
    ret fun(x: i32): str { "bad" }
}

fun main() {
    let f = bad()
    io.println(f(1))
}
