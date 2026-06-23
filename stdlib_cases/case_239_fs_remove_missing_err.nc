import fs
import io

# STDOUT: fs.remove failed
fun main() {
    try fs.remove("__nc_case_239_missing.txt") {
    } else e {
        io.println("fs.remove failed")
    }
}
