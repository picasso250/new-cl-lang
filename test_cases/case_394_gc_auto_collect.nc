# STDOUT: auto GC test passed
# GC 自动触发 —— 实验性验证
#
# 不调 runtime.gc_collect，依靠分配累计超过 64KB 自动触发 GC。
# 关键验证：触发 GC 的那一次分配，新对象不被 GC 误回收。

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
    # 测试 1：多个小分配触发自动 GC，数据不被破坏
    let i: i32 = 0
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
        i += 1
    }

    # 测试 2：分配后立即读取字段，验证触发 GC 的那一次分配存活
    let idx: i32 = 0
    for idx < 100 {
        let cur = new Big { a: i64(idx), b: i64(idx + 1), c: i64(idx + 2),
                            d: i64(idx + 3), e: i64(idx + 4),
                            f: i64(idx + 5), g: i64(idx + 6), h: i64(idx + 7),
                            i: i64(idx + 8), j: i64(idx + 9),
                            k: i64(idx + 10), l: i64(idx + 11), m: i64(idx + 12),
                            n: i64(idx + 13), o: i64(idx + 14),
                            p: i64(idx + 15), q: i64(idx + 16), r: i64(idx + 17),
                            s: i64(idx + 18), t: i64(idx + 19),
                            u: i64(idx + 20), v: i64(idx + 21), w: i64(idx + 22),
                            x: i64(idx + 23), y: i64(idx + 24) }
        # 立即读取字段，验证 cur 不是悬垂指针
        if cur.a != i64(idx) { io.println("FAIL: data corrupted") }
        idx += 1
    }

    io.println("auto GC test passed")
}
