import strings

# ERROR: argument s to strings.contains: expected str, got i32
fun main() {
    strings.contains(1, "x")
}
