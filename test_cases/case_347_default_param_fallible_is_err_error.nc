# ERROR: default parameter ok: fallible operations are not allowed

fun fail(): i32 {
    err "bad"
}

fun bad(ok: bool = fail() is err): bool {
    ok
}

fun main() {
    bad()
}
