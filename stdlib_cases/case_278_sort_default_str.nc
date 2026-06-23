import io
import sort

fun main() {
    let xs = []str { "b", "aa", "a" }
    sort.sort[str](xs)
    for i, item in xs {
        io.println(item)
    }
}

# STDOUT: a
# STDOUT: aa
# STDOUT: b
