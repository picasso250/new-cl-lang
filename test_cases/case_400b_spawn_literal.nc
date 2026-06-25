# case_400b_spawn_literal: spawn with literal
# STDOUT: 42
import io

fun main() {
    spawn fun() {
        io.println(42)
    }
}
