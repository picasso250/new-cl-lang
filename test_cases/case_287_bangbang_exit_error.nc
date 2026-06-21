# STDERR: error: boom
# STDERR: stack:
# STDERR:   at fail (<memory>:8:5)
# STDERR:   at main (<memory>:12:5)
# RC: 1

fun fail(): i32 {
    err "boom"
}

fun main() {
    fail()!!
}
