# STDOUT: 3
# STDOUT: 2
# STDOUT: 1
fun main() {
    defer {
        print(1)
    }
    defer {
        print(2)
    }
    print(3)
}
