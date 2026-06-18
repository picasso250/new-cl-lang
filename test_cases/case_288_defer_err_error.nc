# ERROR: defer cannot return errors

fun main() {
    defer {
        err "bad"
    }
}
