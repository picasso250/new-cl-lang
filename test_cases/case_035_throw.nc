import io
# STDOUT: error: bad path

fun risky(path: str): str {
    if path == "" {
        err "bad path"
    }
    ret "ok"
}

fun main() {
    if risky("") is err {
        io.println("error: bad path")
    }
}
