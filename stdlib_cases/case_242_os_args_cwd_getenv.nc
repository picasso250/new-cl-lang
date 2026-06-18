import fs
import io
import os

fun main() {
    let args = os.args()
    io.println(len(args) > 0)
    io.println(args[0] != "")
    io.println(os.getenv("__NC_TEST_MISSING_ENV__") == "")
    io.println(os.has_env("__NC_TEST_MISSING_ENV__"))
    io.println(os.cwd()!! != "")
    io.println(fs.exists(os.cwd()!!))
}

# STDOUT: 1
# STDOUT: 1
# STDOUT: 1
# STDOUT: 0
# STDOUT: 1
# STDOUT: 1
