# case_405_yield_compute: pure compute loop yields via function entry
# STDOUT: DONE
import io

fun compute() {
    let x = 0
    # pure compute loop — no function calls, no alloc, no yield
    # but outer loop body calls compute() → function entry yield
    for x < 100 {
        let _dummy = x * x
        x = x + 1
    }
}

fun main() {
    spawn fun() {
        let i = 0
        for i < 50 {
            # each compute() call is a function entry → yield check
            compute()
            i = i + 1
        }
        io.println("DONE")
    }
}
