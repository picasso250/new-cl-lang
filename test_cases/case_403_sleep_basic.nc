# case_403_sleep_basic: sleep inside spawn
# STDOUT: A
# STDOUT: B
import io
import sync

extern {
    fun nc_sleep(ms: i32): void = "__nc_sleep"
}

fun main() {
    spawn fun() {
        nc_sleep(100)
        io.println("B")
    }
    spawn fun() {
        io.println("A")
    }
}
