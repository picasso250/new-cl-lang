import io
# STDOUT: hello world
# STDOUT: 1

fun main() {
    let m = map[str,str]{}
    m["greeting"] = "hello world"
    let val = m["greeting"]
    io.println(val)
    let found = m.has("greeting")
    io.println(found)
}
