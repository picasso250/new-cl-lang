import io
import sort

fun main() {
    let us = []u64 { 9u64, 2u64, 7u64 }
    sort.sort[u64](us)
    io.println(us[0])
    io.println(us[2])

    let fs = []f64 { 3.5, 1.25, 2.0 }
    sort.sort[f64](fs)
    io.println(fs[0])
    io.println(fs[2])
}

# STDOUT: 2
# STDOUT: 9
# STDOUT: 1.25
# STDOUT: 3.5
