import io
# STDOUT: ok
# STDOUT: 1
# STDOUT: 0

struct Key { id: i32, name: str }
struct Val { count: i32, label: str }

fun main() {
    let m = map[Key,Val]()
    m[Key { id: 7, name: "a" }] = Val { count: 3, label: "ok" }
    let v = m[Key { id: 7, name: "a" }]
    io.println(v.label)
    io.println(m.has(Key { id: 7, name: "a" }))
    let missing = m[Key { id: 8, name: "b" }]
    io.println(missing.count)
}
