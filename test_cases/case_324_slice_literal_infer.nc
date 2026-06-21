import io

# STDOUT: 3
# STDOUT: b

fun sum(xs: []i32): i32 {
    xs[0] + xs[1]
}

fun second(xs: []str): str {
    xs[1]
}

fun main() {
    io.println(sum([]{1, 2}))
    io.println(second([]{"a", "b"}))
}
