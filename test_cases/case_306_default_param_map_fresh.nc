import io

# STDOUT: 1
# STDOUT: 1

fun put_one(m: map[str,i32] = map[str,i32]()): i32 {
    m["x"] = m["x"] + 1
    m["x"]
}

fun main() {
    io.println(put_one())
    io.println(put_one())
}
