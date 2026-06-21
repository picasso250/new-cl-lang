import io
# STDOUT: 7

fun make(): i32 {
    ret 7
}

fun main() {
    let FOO = make()
    let foo = 1
    foo = FOO
    io.println(foo)
}
