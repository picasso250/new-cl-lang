# STDOUT: auto GC test passed
# GC 自动触发 —— 实验性验证
#
# 不调 runtime.gc_collect，依靠分配累计超过 64KB 自动触发 GC。
# 分配大量大 struct，全部丢弃引用，验证自动 GC 不崩溃。

import runtime
import io

struct Big {
    a: i64, b: i64, c: i64, d: i64, e: i64,
    f: i64, g: i64, h: i64, i: i64, j: i64,
    k: i64, l: i64, m: i64, n: i64, o: i64,
    p: i64, q: i64, r: i64, s: i64, t: i64,
    u: i64, v: i64, w: i64, x: i64, y: i64,
}

fun main() {
    let i: i32 = 0
    # 每轮分配 ~200 字节，~300 轮过 64KB
    for i < 300 {
        let x = new Big { a: i64(i), b: i64(i + 1), c: i64(i + 2),
                          d: i64(i + 3), e: i64(i + 4),
                          f: i64(i + 5), g: i64(i + 6), h: i64(i + 7),
                          i: i64(i + 8), j: i64(i + 9),
                          k: i64(i + 10), l: i64(i + 11), m: i64(i + 12),
                          n: i64(i + 13), o: i64(i + 14),
                          p: i64(i + 15), q: i64(i + 16), r: i64(i + 17),
                          s: i64(i + 18), t: i64(i + 19),
                          u: i64(i + 20), v: i64(i + 21), w: i64(i + 22),
                          x: i64(i + 23), y: i64(i + 24) }
        # x 在每个循环末尾超出作用域，引用丢失
        # 自动 GC 应在累积超过 64KB 时触发回收
        i += 1
    }
    io.println("auto GC test passed")
}
