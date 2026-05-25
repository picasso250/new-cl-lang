# ERROR: nullable pointer type ?*Point: field access requires if p != nil narrowing
struct Point { x: i32 }

fun main() {
    let p: ?*Point = nil
    print(p.x)
}
