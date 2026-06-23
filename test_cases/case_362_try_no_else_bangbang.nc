# STDERR: error: bad
# STDERR: stack:
# STDERR:   at fail (test_cases/case_362_try_no_else_bangbang.nc:8:5)
# STDERR:   at main (test_cases/case_362_try_no_else_bangbang.nc:12:5)
# RC: 1

fun fail(): i32 {
    err "bad"
}

fun main() {
    try value = fail() {
    }
}
