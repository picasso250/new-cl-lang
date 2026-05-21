# ERROR: match expression: else must be the last arm
fun main() {
    let n = 1
    let result = match n {
        else -> 10
        1 -> 20
    }
    print(result)
}
