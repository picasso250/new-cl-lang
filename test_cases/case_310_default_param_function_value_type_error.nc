# ERROR: default parameter cmp: expected fn(i32,i32)->bool, got fn(i32)->bool

fun one_arg(a: i32): bool {
    a == 1
}

fun bad(cmp: fun(i32, i32) bool = one_arg): bool {
    cmp(1, 2)
}

fun main() {
    bad()
}
