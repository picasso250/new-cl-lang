import fs

# ERROR: fs.exists path: expected str, got i32
fun main() {
    fs.exists(1)
}
