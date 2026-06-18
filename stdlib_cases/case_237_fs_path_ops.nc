import fs
import io

# STDOUT: 1
# STDOUT: 1
# STDOUT: 0
# STDOUT: x
# STDOUT: 0
fun main() {
    let dir = "__nc_case_237_dir"
    let file = "__nc_case_237_dir/file.txt"
    let renamed = "__nc_case_237_dir/renamed.txt"

    if fs.exists(renamed) { fs.remove(renamed)!! }
    if fs.exists(file) { fs.remove(file)!! }
    if fs.exists(dir) { fs.remove(dir)!! }

    fs.mkdir(dir)!!
    io.println(fs.exists(dir))

    fs.write_file(file, "x")!!
    io.println(fs.exists(file))

    fs.rename(file, renamed)!!
    io.println(fs.exists(file))
    io.println(fs.read_file(renamed)!!)

    fs.remove(renamed)!!
    fs.remove(dir)!!
    io.println(fs.exists(renamed))
}
