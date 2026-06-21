import io

enum Color {
    Red,
    Green,
}

struct Base {
    x: i32,
}

struct Pair[T,] {
    Base,
    y: T,
}

fun add(
    x: i32,
    y: i32,
): i32 {
    x + y
}

fun apply(
    f: fun(i32,) i32,
    x: i32,
): i32 {
    f(x,)
}

fun inc(x: i32,): i32 {
    x + 1
}

fun (p *Pair[i32,]) sum(extra: i32,): i32 {
    p.x + p.y + extra
}

fun main() {
    let p = Pair[i32,] {
        Base: Base {
            x: 2,
        },
        y: 3,
    }
    let hp = new Pair[i32,] {
        Base: Base {
            x: 4,
        },
        y: 5,
    }
    let nums = []i32 {
        6,
        7,
    }
    let fixed = [2]i32 {
        8,
        9,
    }
    let m = map[str,i32,]()
    m["a"] = 10
    let c = Color::Green

    io.println(add(1, 2,))
    io.println(apply(inc, 4,))
    io.println(p.sum(1,))
    io.println(hp.sum(1,))
    io.println(nums[1])
    io.println(fixed[1])
    io.println(m["a"])
    if c == Color::Green {
        io.println(11)
    }
}

# STDOUT: 3
# STDOUT: 5
# STDOUT: 6
# STDOUT: 10
# STDOUT: 7
# STDOUT: 9
# STDOUT: 10
# STDOUT: 11
