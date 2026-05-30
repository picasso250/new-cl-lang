import io
import runtime

iface Named { fun name(): str }

struct User { n: str }

fun (u *User) name(): str { u.n }

fun main() {
    let n: Named = new User { n: "kept" }
    runtime.gc_collect()
    io.println(n.name())
}

# STDOUT: kept
