# STDERR: error: baz boom
# STDERR: stack:
# STDERR:   at main (test_cases/case_043_uncaught_err.nc:6:5)
# RC: 1
fun main() {
    err "baz boom"
}
