# STDERR: error: bad
# STDERR: stack:
# STDERR:   at fail (<memory>:11:5)
# STDERR:   at wrap (<memory>:15:9)
# STDERR:   at main (<memory>:19:16)
# RC: 1

import io

fun fail(): i32 {
    err "bad"
}

fun wrap(): i32 {
    ret fail()??
}

fun main() {
    io.println(wrap()!!)
}
