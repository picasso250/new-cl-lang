# STDERR: error: method bad
# STDERR: stack:
# STDERR:   at Box.get (<memory>:13:9)
# STDERR:   at main (<memory>:19:39)
# RC: 1

import io

struct Box { ok: bool }

fun (b *Box) get(): i32 {
    if b.ok == false {
        err "method bad"
    }
    ret 1
}

fun main() {
    io.println((new Box { ok: false }).get()!!)
}
