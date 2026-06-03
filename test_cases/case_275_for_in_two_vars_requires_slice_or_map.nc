# ERROR: for-in: expected slice or map, got str

fun main() {
    for k, v in "abc" {
    }
}
