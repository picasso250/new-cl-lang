# STDOUT: ab
fun main() {
    let s = "a" + if true { "b" } else { "c" }
    print(s)
}
