# ERROR: function bad: cannot mix value ret and void ret

fun bad(flag: bool) {
    if flag { ret 1 }
    ret
}

fun main() {
    bad(true)
}
