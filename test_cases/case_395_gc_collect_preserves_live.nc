# STDOUT: pass
# GC 自动触发 —— 保留引用在多次自动回收后存活
#
# 多轮分配-丢弃-保留，触发自动 GC 后验证数据完整。

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
    let round: i32 = 0
    for round < 4 {
        # 每轮分配 200 个 struct，全部丢弃引用
        let i: i32 = 0
        for i < 200 {
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
        # 分配一个大 struct 验证存活
        let live = new Big { a: i64(42), b: i64(43), c: i64(44),
                             d: i64(45), e: i64(46),
                             f: i64(47), g: i64(48), h: i64(49),
                             i: i64(50), j: i64(51),
                             k: i64(52), l: i64(53), m: i64(54),
                             n: i64(55), o: i64(56),
                             p: i64(57), q: i64(58), r: i64(59),
                             s: i64(60), t: i64(61),
                             u: i64(62), v: i64(63), w: i64(64),
                             x: i64(65), y: i64(66) }
        if live.a != i64(42) { io.println("FAIL: live data corrupted") }
        round += 1
    }
    # 总共 4 * 200 = 800 个分配（~160KB payload），自动 GC 应触发多次
    io.println("pass")
}
