# ERROR: let funcs: expected []fun(i32) bool, got []fun(i32) i32

fun main() {
    let funcs: []fun(i32) bool = []{
        fun(x: i32): i32 { x },
    }
}
