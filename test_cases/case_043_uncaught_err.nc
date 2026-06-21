# STDERR: error: baz boom
# STDERR: stack:
# STDERR:   at main (<memory>:6:5)
# RC: 1
fun main() {
    err "baz boom"
}
