import io
# STDOUT: 6
# STDOUT: 6

fun main() {
    let m = map[str,i32]{}
    m["a"] = 1
    m["bb"] = 2
    m["ccc"] = 3
    let key_len_sum = 0
    let value_sum = 0
    for k, v in m {
        key_len_sum = key_len_sum + len(k)
        value_sum = value_sum + v
    }
    io.println(key_len_sum)
    io.println(value_sum)
}
