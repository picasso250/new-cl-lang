import fs
import io

# STDOUT: fs.rename failed
fun main() {
    let a = "__nc_case_240_a.txt"
    let b = "__nc_case_240_b.txt"
    if fs.exists(a) { fs.remove(a)!! }
    if fs.exists(b) { fs.remove(b)!! }
    fs.write_file(a, "a")!!
    fs.write_file(b, "b")!!
    try fs.rename(a, b) {
    } else e {
        io.println("fs.rename failed")
    }
    fs.remove(a)!!
    fs.remove(b)!!
}
