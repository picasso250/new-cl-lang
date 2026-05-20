# STDOUT: 2
fun main() {
    if false {
        defer {
            print(1)
        }
    }
    defer {
        print(2)
    }
}
