import io
# STDOUT: 3
fun main() { struct Point { x: i32, y: i32 }; let p = Point { x: 3, y: 4 }; io.println(p.x) }
