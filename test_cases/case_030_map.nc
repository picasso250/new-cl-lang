# STDOUT: hello world
# STDOUT: 1

fun main() {
    let mut m = map_new()
    map_set_s(m, "greeting", "hello world")
    let val = map_get_s(m, "greeting")
    print(val)
    let found = map_has(m, "greeting")
    print(found)
}
