# case_404_gc_stress: spawns with captured values, trigger GC via batch alloc
# STDOUT: SAFE
import io

fun main() {
    let n = 50
    let i = 0
    # spawn many Gs — each captures a value (root-protected by gc_root_handle)
    for i < n {
        spawn fun() {
            let _x = i  # captured env has gc root
        }
        i = i + 1
    }
    io.println("SAFE")
}
