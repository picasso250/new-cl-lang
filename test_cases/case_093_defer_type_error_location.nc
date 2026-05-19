# ERROR: 4:9: print: expected 1 args, got 2
fun main() {
    defer {
        print(1, 2)
    }
}
