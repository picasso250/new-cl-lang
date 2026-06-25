# NC 并发模型 — M:N 绿色线程

> 本文档记录 NC 的并发模型设计与实现边界。语言层概要见 `design.md`。

## 目标

NC 使用 **M:N 绿色线程**（类似 Go goroutine）实现并发：

- N 个轻量用户态线程（green thread）由 M 个 OS worker（M = runtime.NumCPU）调度
- `go f()` 关键字启动新 green thread
- `sync.Mutex` 标准库提供互斥同步
- `sleep` 提供定时 yield
- 目标：并行计算密集型任务与阻塞模拟（I/O netpoller 推迟到 v2）

## 驱动 case

```nc
fun main() {
    go funcA()
    go funcB()
}
```

两个 green thread 并发执行，main 等待两者结束后 exit。

## 语言表面

### `go` 关键字

- 只接受函数调用：`go funcA()`、`go obj.method()`、`go fun() { ... }()`
- 语句，不是表达式，不产生值，不能用于赋值、参数或 `ret`
- 闭包允许：`go fun() { io.println("hello") }()`

### 函数序言 yield 检查

编译器在每个函数入口插入检查：若当前 green thread 已运行超过一个时间片（默认 10ms），则 yield 到调度器。该检查由 LLVM 后端在函数 prologue 中生成。

## 调度器

### 架构

调度器实现在 ncrt（C），作为 runtime 的一部分。

### Green thread 状态机

```
G_RUNNABLE       在 run queue 中，等待被调度
G_RUNNING        正在某个 worker 上执行
G_WAIT_MUTEX     阻塞在 sync.Mutex.lock() 上
G_WAIT_TIMER     阻塞在 sleep() 上（timer 未到期）
G_DEAD           已退出（由调度器回收栈）
```

### M 个 worker

- M = `runtime.NumCPU()`，启动时创建
- 用户可通过 `runtime.set_maxprocs(n)` 覆盖
- 每个 worker 是一个 OS 线程，运行调度循环
- worker 不直接决定进程退出；由 runtime 主控制流在确认所有 green thread 结束后统一 exit

### 全局 run queue

- 所有 `G_RUNNABLE` green thread 排在一个全局队列中
- 一个 mutex 保护队列
- 所有 worker 从同一个队列取 task
- v1 不做本地队列 + 工作窃取（work stealing）

### 调度循环

```
while True:
    wake_expired_timers()         // 每轮都检查 timer，不只在 queue 空时

    g = pop_run_queue()
    if g != null:
        g.state = G_RUNNING
        run(g)                    // 跳转到 green thread 栈执行
        // g 返回后回到此处；g 已变为 G_DEAD 或被重新放回 run queue
        continue

    // run queue 为空
    if shutdown_conditions_met():
        break                     // worker 退出调度循环

    // 等待：有新 timer 到期，或有 G 进入 run queue
    wait_until(next_timer_deadline or run_queue_nonempty)
```

### main 与 green thread 生命周期

- `main` 本身作为一个 green thread 运行，`live_count` 初始为 1
- `go f()` 时 `user_g_count` +1，新 G 放入 run queue
- green thread 正常退出时 `user_g_count` -1
- green thread 因 `err` 传播到顶部而 abort 时 `user_g_count` -1
- `main` 函数体结束后，运行时标记 `main_done = true`，main 的 G 变为 `G_DEAD`，`live_count` -1

### Worker 退出条件

```
shutdown_conditions_met():
    return (main_done          // main 已结束
        and user_g_count == 0  // 所有用户 green thread 已退出
        and run_queue_empty()
        and timer_heap_empty())
```

只有 runtime 主控制流（非 worker）在所有 worker 退出后调 `exit(0)`。worker 本身不调 `exit`。

此设计保证 `main` 结束之前进程不会退出；`main` 结束后，所有 `go` 出来的 green thread 也退出后，才会退出。

### 死锁检测

在每个调度循环轮内，如果 run queue 为空且所有 live G 都处于：

```
G_WAIT_MUTEX | G_WAIT_TIMER
```

且 `timer_heap` 为空（即没有任何即将到期的 timer），调度器认定不可继续，产生 **"all green threads are asleep - deadlock"** panic。

对于 timer 不为空的情况，调度器可正常阻塞等待 timer，不属于死锁。

## 栈管理

### 固定 64KB 栈 + Guard Page

- 每个 green thread 的栈 = **1 个 guard page（no-access）+ 64KB usable 栈**
- 使用 `mmap`（Linux）或 `VirtualAlloc`（Windows）分配，guard page 设为 `PROT_NONE` / `PAGE_NOACCESS`
- 栈溢出触发确定的 segfault / access violation crash，不会静默破坏 heap 内存
- v1 不做动态栈增长或分段栈
- 编译器不做栈溢出静态检测

### Guard page 实现要点

- Linux：`mmap(stack_addr, guard_size + usable_size, ...)`，对 guard page 调 `mprotect(addr, guard_size, PROT_NONE)`
- Windows：`VirtualAlloc(stack_addr, guard_size, MEM_RESERVE)` 作为 guard，`VirtualAlloc(stack_addr + guard_size, usable_size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE)` 作为可用栈

### 新 green thread 初始栈要求

- 栈必须 16-byte 对齐（x64 SysV 和 Win64 都有此要求）
- Windows x64：初始栈顶部需预留 32 字节 shadow space（返回地址占 8，shadow 占 32，共 40 字节），后续第一次函数调用时作为 ABI shadow space 使用

### 栈切换（汇编）

上下文切换通过汇编实现，每个目标架构 <50 行：

**Linux x86_64 (SysV ABI)**

保存/恢复 callee-saved 寄存器：
```
RBX, RBP, RSP, R12, R13, R14, R15
```

SysV x86_64 有 128 字节 red zone。NC 编译器和 runtime 代码编译时禁用 red zone（`-mno-red-zone`），避免切栈时踩到被切 green thread 的红区。

**Windows x64**

保存/恢复 callee-saved 寄存器：
```
RBX, RBP, RDI, RSI, RSP, R12, R13, R14, R15
XMM6, XMM7, XMM8, XMM9, XMM10, XMM11, XMM12, XMM13, XMM14, XMM15
```

Windows x64 没有 red zone。无需特殊处理。

### GC 栈扫描

GC 扫描时，对所有 green thread：
- `G_RUNNING`（正在运行的）：使用当前线程栈 + 各 worker 自己声明的 GC root
- `G_RUNNABLE` / `G_WAIT_MUTEX` / `G_WAIT_TIMER`（挂起的）：从保存的 `%rsp` 起，按 8 字节对齐扫描整个 64KB 栈
- v1 先做保守扫描（标记对齐 slot 是否为指针），不做精确 stack map

## 同步原语

### sync.Mutex（标准库）

编译器零改动。`sync.Mutex` 是标准库类型，内部调用 ncrt 的 C 实现。

```c
struct nc_mutex {
    nc_spinlock internal;          // 保护 state + wait queue
    int locked;                     // 0 = unlocked, 1 = locked
    nc_green_thread *head;          // 等待队列头
    nc_green_thread *tail;          // 等待队列尾
};
```

#### lock 语义

```text
lock(internal)
if locked == 0:
    locked = 1
    unlock(internal)
    return
else:
    g = current_green_thread()
    enqueue(g)                     // 挂到等待队列
    g.state = G_WAIT_MUTEX
    // 关键：below 这一行和 unlock + yield 之间的 window 必须原子；
    // nc_spinlock internal 保护了这一段
    unlock(internal)
    yield_to_scheduler()           // 交出控制权，等待被 unlock 方唤醒
    // 醒来时：locked 已经为 true，当前 G 已经拥有锁，跳到 return
    return
```

#### unlock 语义

```text
lock(internal)
if wait_queue 非空:
    g = dequeue()
    g.state = G_RUNNABLE
    enqueue_global_run_queue(g)
    // 关键：locked 保持为 true，所有权直接转交给 g
    // 不对 locked 做任何改动
    // g 醒来后已经持有锁，不需要重新 CAS
else:
    locked = 0
unlock(internal)
```

这是 **handoff mutex**：锁的所有权不经过 `locked == 0` 中间态，而是在等待队列上直接转交。避免丢失唤醒、避免惊群。

#### 不支持

- `try_lock`（v1 不做）
- 可重入锁（v1 不做）

## 定时器与 sleep

`sleep(ms: i32)` 标准库函数由 ncrt 实现：

1. 将当前 green thread 状态设为 `G_WAIT_TIMER`，挂到全局 timer 优先队列（最小堆，按唤醒时间排序）
2. yield 到调度器
3. 调度器**每轮**都会调用 `wake_expired_timers()`：取出所有过期 timer，将对应的 green thread 改回 `G_RUNNABLE` 并放入 run queue

timer 优先队列内部用 `nc_spinlock` 保护，最小时间复杂度的插入/删除。

```text
wake_expired_timers():
    lock(timer_heap)
    while timer_heap.min ≤ now:
        g = pop_min(timer_heap)
        g.state = G_RUNNABLE
        enqueue_global_run_queue(g)
    unlock(timer_heap)
```

## yield 机制

### 合作式 yield

编译器在**每个函数入口**插入一段代码：

```
if (当前 green thread 已运行超过时间片阈值（默认 10ms）) {
    yield_to_scheduler()
}
```

### LLVM 实现

1. ncrt 维护每个 green thread 的 `start_ticks`（进入 `G_RUNNING` 时的时钟滴答）
2. LLVM 后端在函数 prologue 中生成：load 当前 G 的 `start_ticks`，与当前 `__nc_ticks()` 比较，超过时间片则调用 `__nc_yield()`
3. `__nc_yield()`：将当前 G 的上下文保存到 G 结构，置 `G_RUNNABLE`，放入全局 run queue，进入调度器选下一个 G

### 限制

- **纯循环无函数调用则不会 yield**（如 `while true { x += 1 }`）。这在 v1 是可接受的限制——该 G 会持续占用一个 worker，但其他 worker 不受影响
- 该限制在 v2 中由异步抢占或 loop backedge safepoint 解决

## GC 与并发

### GC safepoint

NC v1 使用**完全合作式的 GC safepoint**，不使用信号/APC 异步抢占。

safepoint 在以下位置触发：

```
1. 每个函数入口（即函数序言中的 yield 检查点）
2. 每个 for / while 循环的 backedge（`for condition { ... }` 的 `}` 处）
3. 每次 gc_alloc 前
```

LLVM 后端负责在 loop backedge 处插入 safepoint poll。编译时识别 `ForAst`（条件循环）和 range loop（`for i, item in items`），在每次迭代结束前插入：

```
if (__nc_safepoint_needed) {
    __nc_gc_safepoint()
}
```

当 GC 需要 STW 时：
1. `__nc_gc_safepoint_needed` 被置为 true
2. 所有 green thread 在下一个 safepoint 处停止
3. STW 完成后，`__nc_gc_safepoint_needed` 被置为 false
4. green thread 恢复执行

纯热循环（如 `while true { x += 1 }`）即使没有函数调用，也有 loop backedge safepoint，因此总能响应 GC STW。

### 分配

- green thread 的内存分配直接调用 ncrt 的 `gc_alloc`，不加 per-thread cache
- v1 不做 per-P 内存分配缓存（如 Go 的 mcache）

## v1 边界

### v1 包含

| 特性 | 状态 |
|---|---|
| `go` 关键字 | 编译器 |
| 汇编上下文切换（x64 win/linux） | ncrt |
| M 个 worker + 全局 run queue | ncrt |
| 合作式 yield（函数序言 + loop backedge + alloc 点） | 编译器 + ncrt |
| 64KB 固定栈 + guard page | ncrt |
| main 为 green thread + 等所有用户 G 退出 | ncrt |
| G 状态机（RUNNABLE/RUNNING/WAIT_MUTEX/WAIT_TIMER/DEAD） | ncrt |
| all-asleep 死锁 panic | ncrt |
| `sync.Mutex`（handoff ownership 标准库） | 标准库 + ncrt |
| `sleep`（timer 每轮检查） | ncrt |
| GC STW（完全合作式 safepoint） | 编译器 + ncrt |

### v1 明确不包含

| 特性 | 原因 |
|---|---|
| channel / select | 无 case 驱动；语法和 lowering 成本高 |
| TCP I/O netpoller | 无 case 驱动；epoll/kqueue/IOCP 工作量大 |
| 文件 I/O 非阻塞包装 | 需要 io_uring 或相似技术 |
| 工作窃取调度 | 全局队列在 v1 场景足够 |
| 异步抢占（信号/APC） | 合作式 yield + loop backedge 在 v1 可接受 |
| 动态栈增长 | 实现复杂且无 case 证明必要性 |
| 可观测性 / debug 基础设施 | 无 case 驱动 |
| per-P 内存分配缓存 | 先通后优 |
| `try_lock` | 无 case 驱动 |
| 可重入锁 | 无 case 驱动 |

## 后续方向（v2 / case 驱动）

- **channel + select**：标准库 `chan.Chan[T]` + 编译器 `select` 构造
- **TCP netpoller**：epoll/kqueue/IOCP 事件循环寄生在 worker 中
- **工作窃取**：本地队列 + 偷取，降低全局队列锁竞争
- **动态栈增长**：达到风险监控范围
- **通用异步抢占**：信号驱动的抢占式调度，消除热循环不 yield 问题
