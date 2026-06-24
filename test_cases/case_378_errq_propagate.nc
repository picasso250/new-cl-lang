import io

fun load(): str {
    err "missing"
}

fun wrap(): str err {
    load() err? e {
        err e
    }
}

fun main() {
    let text = wrap()!!
    io.println(text)
}

# STDERR: error: missing
# STDERR: stack:
# STDERR:   at load (test_cases/case_378_errq_propagate.nc:4:5)
# STDERR:   at wrap (test_cases/case_378_errq_propagate.nc:8:5)
# STDERR:   at wrap (test_cases/case_378_errq_propagate.nc:9:9)
# STDERR:   at main (test_cases/case_378_errq_propagate.nc:14:16)
# RC: 1
