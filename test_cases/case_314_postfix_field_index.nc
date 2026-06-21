import io

struct P { s: str }
struct Bag { items: []i32 }
struct Entry { value: i32 }
struct Obj { entries: []Entry }

fun main() {
    let i = 1
    let p = P { s: "az" }
    let arr = Bag { items: []i32 { 10, 20 } }
    let obj = Obj { entries: []Entry { Entry { value: 30 }, Entry { value: 40 } } }
    let lit = "hi"

    io.println(p.s[i])
    io.println(arr.items[i])
    io.println(obj.entries[i].value)
    io.println(lit[i])
}

# STDOUT: 122
# STDOUT: 20
# STDOUT: 40
# STDOUT: 105