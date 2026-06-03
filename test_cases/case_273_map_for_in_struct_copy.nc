import io
# STDOUT: 10
# STDOUT: 12

struct Key { id: i32, name: str }
struct Val { count: i32, label: str }

fun main() {
    let m = map[Key,Val]()
    m[Key { id: 2, name: "aa" }] = Val { count: 5, label: "x" }
    m[Key { id: 3, name: "bbb" }] = Val { count: 7, label: "y" }
    let key_score = 0
    let value_sum = 0
    for k, v in m {
        key_score = key_score + k.id + len(k.name)
        value_sum = value_sum + v.count
    }
    io.println(key_score)
    io.println(value_sum)
}
