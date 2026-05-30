import io

iface Value { fun get(): i32 }

struct A { value: i32 }
struct B { value: i32 }

fun (a *A) get(): i32 { a.value }
fun (b *B) get(): i32 { b.value + 10 }

fun show(v: Value) {
    io.println(v.get())
}

fun main() {
    show(new A { value: 3 })
    show(new B { value: 3 })
}

# STDOUT: 3
# STDOUT: 13
