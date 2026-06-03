import io
# STDOUT: 6
# STDOUT: 12

fun main() {
    let m = map[i32,str]()
    m[1] = "aa"
    m[2] = "bbb"
    m[3] = "c"
    let key_sum = 0
    let value_len_sum = 0
    for k, v in m {
        key_sum = key_sum + k
        value_len_sum = value_len_sum + len(v)
    }
    io.println(key_sum)
    io.println(value_len_sum + len(m[1]) + len(m[2]) + len(m[3]))
}
