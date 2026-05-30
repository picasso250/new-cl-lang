# ERROR: string interpolation: cannot convert []i32 to str
import io
fun main() {
    let xs = []i32 { 1 }
    io.println("xs={xs}")
}
