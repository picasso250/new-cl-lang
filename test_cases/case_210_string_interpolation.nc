# STDOUT: Hello, NC
# STDOUT: sum=7
# STDOUT: r=A
# STDOUT: {x}
# STDOUT: v=42
import io

struct User { name: str }

fun inc(x: i32): i32 { ret x + 1 }

fun main() {
    let name = "NC"
    let a = 3
    let b = 4
    let r = 'A'
    let user = User { name: "Ada" }
    let xs = []i32 { 41 }
    io.println("Hello, {name}")
    io.println("sum={a + b}")
    io.println("r={r}")
    io.println("{{x}}")
    io.println("v={inc(xs[0])}")
}
