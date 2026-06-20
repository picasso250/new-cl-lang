import io

# STDOUT: 1
# STDOUT: 1

fun push_one(xs: []i32 = []i32{}): i32 {
    xs = append(xs, 1)
    len(xs)
}

fun main() {
    io.println(push_one())
    io.println(push_one())
}
