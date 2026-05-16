# STDOUT: a
# STDOUT: b
# STDOUT: c
fun main() {
    let mut s = []str { "a", "b" }
    s = append(s, "c")
    for i, item in s {
        print(item)
    }
}
