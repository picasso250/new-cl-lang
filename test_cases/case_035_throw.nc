import io
# STDOUT: error: bad path

fun risky(path: str): str {
    if path == "" {
        throw "bad path"
    }
    return "ok"
}

fun main() {
    try {
        let s = risky("")
        io.println(s)
    } catch e {
        io.println("error: " + e)
    }
}
