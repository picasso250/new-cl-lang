import io

# STDOUT: one
# STDOUT: two

fun main() {
    let m = map{1: "one", 2: "two"}
    io.println(m[1])
    io.println(m[2])
}
