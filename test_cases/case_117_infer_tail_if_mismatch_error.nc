# ERROR: if expression branches: expected i32, got str

fun bad(flag: bool) {
    if flag { 1 } else { "x" }
}

fun main() {
    bad(true)
}
