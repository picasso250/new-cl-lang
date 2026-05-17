# ERROR: switch case: expected i32, got bool
fun main() {
    let x = 1
    switch x {
        true -> print(1)
    }
}
