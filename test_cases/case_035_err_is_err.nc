import io
# STDOUT: error: bad path

fun risky(path: str): str {
    if path == "" {
        err "bad path"
    }
    ret "ok"
}

fun main() {
    try value = risky("") {
        io.println(value)
    } else e {
        io.println("error: bad path")
    }
}
