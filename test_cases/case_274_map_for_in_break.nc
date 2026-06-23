import io
# STDOUT: 1

fun main() {
    let m = map[str,i32]{}
    m["a"] = 1
    m["b"] = 2
    let count = 0
    for k, v in m {
        count = count + 1
        break
    }
    io.println(count)
}
