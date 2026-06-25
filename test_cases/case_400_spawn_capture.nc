# case_400_spawn_capture: spawn with captured i32
# STDOUT: 42
import io

fun main() {
    let x = 42
    spawn fun() {
        io.println(x)
    }
}
