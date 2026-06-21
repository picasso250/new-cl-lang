# STDERR: error: method bad
# STDERR: stack:
# STDERR:   at Box.get (test_cases/case_329_err_stack_method.nc:13:9)
# STDERR:   at main (test_cases/case_329_err_stack_method.nc:19:39)
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
