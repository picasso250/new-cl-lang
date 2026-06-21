# STDERR: error: bad
# STDERR: stack:
# STDERR:   at fail (test_cases/case_328_err_stack_propagate.nc:11:5)
# STDERR:   at wrap (test_cases/case_328_err_stack_propagate.nc:15:9)
# STDERR:   at main (test_cases/case_328_err_stack_propagate.nc:19:16)
# RC: 1

import io

fun fail(): i32 {
    err "bad"
}

fun wrap(): i32 {
    ret fail()??
}

fun main() {
    io.println(wrap()!!)
}
