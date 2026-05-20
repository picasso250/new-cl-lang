# ERROR: function f: return type inference cycle; add explicit return type

fun f() { g() }
fun g() { f() }

fun main() {
    f()
}
