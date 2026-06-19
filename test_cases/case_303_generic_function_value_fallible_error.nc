# ERROR: fallible functions cannot be used as function values

fun maybe[T](x: T): T {
    err "no"
}

fun main() {
    let f = maybe[i32]
}
