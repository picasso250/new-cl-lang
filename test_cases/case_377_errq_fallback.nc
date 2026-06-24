import io

fun load(ok: bool): str {
    if ok {
        "loaded"
    } else {
        err "missing"
    }
}

fun main() {
    let a = load(true) err? e {
        "fallback"
    }
    let b = load(false) err? e {
        io.println("recover")
        "fallback"
    }
    io.println(a)
    io.println(b)
}

# STDOUT: recover
# STDOUT: loaded
# STDOUT: fallback
