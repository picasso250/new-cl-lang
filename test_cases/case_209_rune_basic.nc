# STDOUT: A
# STDOUT: 中
# STDOUT: A!
# STDOUT: 1
# STDOUT: 65
import io

fun id(r: rune): rune { ret r }

fun main() {
    let a = 'A'
    let b: rune = '\u{4E2D}'
    io.println(a)
    io.println(id(b))
    io.println(str(a) + "!")
    io.println(a == 'A')
    io.println(i32(a))
}
