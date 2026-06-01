import fs

# ERROR: argument path to fs.exists: expected str, got i32
fun main() {
    fs.exists(1)
}
