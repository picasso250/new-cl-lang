# ERROR: function bad: cannot mix value return and void return

fun bad(flag: bool) {
    if flag { return 1 }
    return
}

fun main() {
    bad(true)
}
