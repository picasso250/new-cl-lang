# ERROR: promoted field x conflicts
struct A { x: i32 }
struct C { x: i32 }
struct B { A, C }

fun main() {}
