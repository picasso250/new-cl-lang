# STDERR: error: boom
# STDERR: stack:
# STDERR:   at fail (test_cases/case_287_bangbang_exit_error.nc:8:5)
# STDERR:   at main (test_cases/case_287_bangbang_exit_error.nc:12:5)
# RC: 1

fun fail(): i32 {
    err "boom"
}

fun main() {
    fail()!!
}
