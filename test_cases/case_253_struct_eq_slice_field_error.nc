# ERROR: comparison: type []i32 is not comparable
struct Bag { items: []i32 }

fun main() {
    let a = Bag { items: []i32 { 1, 2 } }
    let b = Bag { items: []i32 { 1, 2 } }
    a == b
}
