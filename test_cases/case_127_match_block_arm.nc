# STDOUT: 7
fun main() {
    let n = 1
    let result = match n {
        0 -> 0
        else -> {
            let base = 3
            base + 4
        }
    }
    print(result)
}
