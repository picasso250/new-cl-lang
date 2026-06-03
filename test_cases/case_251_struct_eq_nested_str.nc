import io
# STDOUT: 1
# STDOUT: 0
struct Name { first: str, last: str }
struct User { id: i32, name: Name }

fun main() {
    let a = User { id: 7, name: Name { first: "Ada", last: "Lovelace" } }
    let b = User { id: 7, name: Name { first: "Ada", last: "Lovelace" } }
    let c = User { id: 7, name: Name { first: "Ada", last: "Byron" } }
    io.println(a == b)
    io.println(a == c)
}
