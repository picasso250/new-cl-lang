import io

# STDOUT: missing

fun load(): str {
    err "not found"
}

fun main() {
    try value = load() {
        io.println(value)
    } else e {
        let label = match e {
            "not found" -> "missing"
            else -> "other"
        }
        io.println(label)
    }
}
