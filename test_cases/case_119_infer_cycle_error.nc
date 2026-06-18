# ERROR: function f: ret type inference cycle; add explicit ret type

fun f() { g() }
fun g() { f() }

fun main() {
    f()
}
