# STDOUT: <memory>
# STDOUT: 14
# STDOUT: 16
# STDOUT: show
# STDOUT: Box.name
# STDOUT: lambda 0

import io

struct Box { value: i32 }

fun show() {
    io.println(__FILE__)
    io.println(__LINE__)
    io.println(__COL__)
    io.println(__FUNC__)
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
