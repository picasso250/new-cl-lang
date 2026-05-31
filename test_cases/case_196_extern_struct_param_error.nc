# ERROR: extern function take_point: unsupported parameter p: Point

struct Point { x: i32 }

extern {
    fun take_point(p: Point): i32
}

fun main() {}
