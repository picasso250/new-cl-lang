# case_396_spawn_basic: minimal spawn test
# STDOUT: child
import io

fun main() {
    spawn fun() {
        io.println("child")
    }
}
