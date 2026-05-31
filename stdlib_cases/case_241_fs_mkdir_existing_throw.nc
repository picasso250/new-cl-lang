import fs
import io

# STDOUT: fs.mkdir failed
fun main() {
    let dir = "__nc_case_241_dir"
    if fs.exists(dir) { fs.remove(dir) }
    fs.mkdir(dir)
    try {
        fs.mkdir(dir)
    } catch e {
        io.println(e)
    }
    fs.remove(dir)
}
