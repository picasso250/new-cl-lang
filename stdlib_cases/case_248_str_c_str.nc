import io
import os

extern {
    fun strlen(p: *i8): u64
}

# STDOUT: 0
# STDOUT: 3
# STDOUT: 2
# STDOUT: 3
# STDOUT: 0
# STDOUT: 1
fun main() {
    io.println(strlen("".c_str()))
    io.println(strlen(("a" + "bc").c_str()))
    io.println(strlen("abcd"[1:3].c_str()))
    io.println(strlen("x={1}".c_str()))
    io.println(strlen(os.getenv("__NC_CASE_248_MISSING").c_str()))
    io.println(strlen((os.cwd()!!).c_str()) > 0u64)
}
