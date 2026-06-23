import io

fun main() {
    io.println("a" < "b")
    io.println("a" <= "a")
    io.println("b" > "a")
    io.println("b" >= "b")
    io.println("a" < "aa")
    io.println("" < "a")
    io.println("中" > "a")
}

# STDOUT: 1
# STDOUT: 1
# STDOUT: 1
# STDOUT: 1
# STDOUT: 1
# STDOUT: 1
# STDOUT: 1
