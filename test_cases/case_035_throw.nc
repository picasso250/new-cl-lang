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
        print(s)
    } catch e {
        print("error: " + e)
    }
}
