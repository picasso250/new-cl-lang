# case_399_closure_capture: closure capture without spawn
# STDOUT: 42
import io

fun main() {
    let x = 42
    let f = fun() {
        io.println(x)
    }
    f()
}
