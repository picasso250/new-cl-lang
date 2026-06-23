import io

# STDOUT: cleanup failed

fun cleanup() {
    err "cleanup"
}

fun main() {
    try cleanup() {
        io.println("ok")
    } else e {
        io.println("cleanup failed")
    }
}
