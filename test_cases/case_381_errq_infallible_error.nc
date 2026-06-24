# ERROR: err? requires a fallible call

fun main() {
    let x = 1 err? e {
        2
    }
}
