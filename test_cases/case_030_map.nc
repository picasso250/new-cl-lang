# STDOUT: hello world
# STDOUT: 1

fun main() {
    let m = map_new()
    m["greeting"] = "hello world"
    let val = m["greeting"]
    print(val)
    let found = map_has(m, "greeting")
    print(found)
}
