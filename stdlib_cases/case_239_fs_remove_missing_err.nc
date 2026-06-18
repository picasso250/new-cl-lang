import fs
import io

# STDOUT: fs.remove failed
fun main() {
    if fs.remove("__nc_case_239_missing.txt") is err {
        io.println("fs.remove failed")
    }
}
