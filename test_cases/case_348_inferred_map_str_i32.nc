import io

# STDOUT: 7
# STDOUT: 9
# STDOUT: 16

fun main() {
    let m = map{"a": 7, "b": 9}
    io.println(m["a"])
    io.println(m["b"])
    let sum = 0
    for _key, value in m {
        sum += value
    }
    io.println(sum)
}
