# STDOUT: many
fun main() {
    let n = 3
    let label = match n {
        0 -> "zero"
        1 -> "one"
        else -> "many"
    }
    print(label)
}
