# STDOUT: test_cases/case_331_magic_consts.nc
# STDOUT: 15
# STDOUT: 16
# STDOUT: show
# STDOUT: test_cases
# STDOUT: Box.name
# STDOUT: lambda 0

import io

struct Box { value: i32 }

fun show() {
    io.println(__FILE__)
    io.println(__LINE__)
    io.println(__COL__)
    io.println(__FUNC__)
    io.println(__MODULE__)
}

fun (b *Box) name() {
    io.println(__FUNC__)
}

fun main() {
    show()
    let b = new Box { value: 1 }
    b.name()
    let f: fun() void = fun() {
        io.println(__FUNC__)
    }
    f()
}
