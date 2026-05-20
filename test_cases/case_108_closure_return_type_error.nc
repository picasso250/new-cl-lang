# ERROR: return: expected fn(i32)->i32, got fn(i32)->str
fun bad(): (i32) -> i32 {
    return fun(x: i32): str { "bad" }
}

fun main() {
    let f = bad()
    print(f(1))
}
