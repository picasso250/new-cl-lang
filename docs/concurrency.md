# NC 并发模型 — M:N 绿色线程

> 本文档记录 NC 的并发模型设计与实现边界。语言层概要见 `design.md`。

## 目标

NC 使用 **M:N 绿色线程**（类似 Go goroutine）实现并发：

- N 个轻量用户态线程（green thread）由 M 个 OS worker（M = runtime.NumCPU）调度
- `go f()` 关键字启动新 green thread
- `sync.Mutex` 标准库提供互斥同步
- `sleep` 提供定时 yield
- 目标：并行计算密集型任务与 blocking 模拟（I/O netpoller 推迟到 v2）

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
- 语句，不返回任何值。`go` 表达式本身类型为 `void`
- 闭包允许：`go fun() { io.println("hello") }()`
- 不可以在表达式位置使用

### 函数序言 yield 检查

编译器在每个函数入口插入检查：若当前 green thread 已运行超过一个时间片（默认 10ms），则 yield 到调度器。该检查由 LLVM 后端在函数 prologue 中生成。

## 调度器

### 架构

调度器实现在 ncrt（C），作为 runtime 的一部分。

### M 个 worker

- M = `runtime.NumCPU()`，启动时创建
- 用户可通过 `runtime.set_maxprocs(n)` 覆盖
- 每个 worker 是一个 OS 线程，运行调度循环

### 全局 run queue

- 所有就绪 green thread 排在一个全局队列中
- 一个 mutex 保护队列
- 所有 worker 从同一个队列取 task
- v1 不做本地队列 + 工作窃取（work stealing）

### 调度循环

```
while True:
    lock(global_queue)
    if global_queue 不为空:
        g = pop(global_queue)
        unlock(global_queue)
        run(g)  # 跳转到 green thread 栈执行
        # g yield 后回到此处，将 g.finished? 放回或销毁
    else:
        unlock(global_queue)
        # 检查 timer 队列
        if 有 timer 就绪:
            wake 对应的 green thread，continue
        elif 活 green thread 计数 == 0:
            exit(0)  # main 等完了所有 green thread
        else:
            yield_to_os()  # 让出 OS 时间片，避免 busy spin
```

### Live green thread 计数

- `go f()` 时计数 +1
- green thread 正常退出时计数 -1
- green thread 因 `err` 传播到顶部而 abort 时计数 -1
- main 函数体结束后，持有 main 的 worker 开始等待计数归零

### 死锁检测

当所有 green thread 都阻塞在 channel（v2）/mutex 上且没有 timer 待触发时，调度器检测到所有 green thread 无法继续推进，产生 **"all green threads are asleep - deadlock"** panic。v1 限于 mutex 场景。

## 栈管理

### 固定 64KB 栈

- 每个 green thread 启动时分配 64KB 连续内存
- 不增长。函数调用超过 64KB 会导致栈溢出 crash
- v1 不做动态栈增长或分段栈
- 编译器不做栈溢出静态检测，运行时也不做栈边界检查

### 栈切换（汇编）

上下文切换通过汇编实现，每个目标架构 <50 行：

- 保存/恢复 callee-saved 寄存器（x64: R12-R15, RBX, RBP, RSP）
- 切换 `%rsp` 到目标 green thread 的栈顶
- Windows x64 和 Linux x64 各一份实现

### GC 栈扫描

GC 扫描时，对所有 green thread：
- 使用当前线程栈（正在运行的 green thread）+ 各 worker 栈上声明的 conservative scan
- 挂起的 green thread：从保存的 `%rsp` 起，按 8 字节对齐扫描整个 64KB 栈
- v1 先做保守扫描（标记对齐 slot 是否为指针），不做精确 stack map

## 同步原语

### sync.Mutex（标准库）

编译器零改动。`sync.Mutex` 是标准库类型，内部调用 ncrt 的 C 实现：

```c
struct nc_mutex {
    atomic i32 state;       // 0 = unlocked, 1 = locked
    nc_green_thread *head;  // 等待队列（单链表）
};

void __nc_mutex_lock(nc_mutex *m);
void __nc_mutex_unlock(nc_mutex *m);
```

- lock：CAS 尝试获取，失败则 yield，挂到 m 的等待队列
- unlock：标记为 unlocked，wake 等待队列头部的 green thread
- 不支持 try_lock，不支持可重入

## 定时器与 sleep

`sleep(ms: i32)` 标准库函数由 ncrt 实现：

1. 将当前 green thread 挂到 ncrt 全局 timer 优先队列（按唤醒时间排序）
2. yield 到调度器
3. 调度器在全局队列为空时检查 timer 队列：若最小值已超时，将对应 green thread 放回 run queue

## yield 机制

### 合作式 yield

编译器在**每个函数入口**插入一段代码：

```
if (当前 green thread 的 runtime 已超过 10ms) {
    yield_to_scheduler()
}
```

实现方式：

1. ncrt 维护 per-green-thread 的 start_time（进入 running 时的 ticks）
2. 函数入口检查通过 LLVM IR 生成：load green thread 上下文中的 start_time，与当前 ticks 比较，超时则调用 `__nc_yield()`
3. `__nc_yield()`：保存当前上下文到 green thread 结构，将自身放回全局 run queue 尾部，调用调度器选择下一个 green thread

### 限制

- **纯循环无函数调用则不会 yield**（如 `while true { x += 1 }`）。这会卡住一个 worker，但其他 M-1 个 worker 不受影响
- GC STW 通过窄化异步抢占解决（见下文）

## GC 与并发

### GC safepoint

- 普通 GC `runtime.gc_collect()` 需要所有 green thread 到达 safepoint
- v1 中的 GCC 使用**窄化异步抢占**：仅当 GC 需要 STW 时，向所有 worker 发送信号（Linux SIGURG / Windows QueueUserAPC），强制 green thread 停到 GC safepoint
- GC safepoint 即为函数入口的 yield 检查点——此时栈是安全的，因为不在函数调用中间
- 非 GC 时，不做异步抢占

### 分配

- green thread 的内存分配直接调用 ncrt 的 `malloc`/`gc_alloc`，不加 per-thread cache
- v1 不做 per-P 内存分配缓存（如 Go 的 mcache）

## v1 边界

### v1 包含

| 特性 | 状态 |
|---|---|
| `go` 关键字 | 编译器 |
| 汇编上下文切换（x64 win/linux） | ncrt |
| M 个 worker + 全局 run queue | ncrt |
| 合作式 yield（函数序言检查） | 编译器 + ncrt |
| 64KB 固定栈 | ncrt |
| main 等待所有 green thread | ncrt |
| 活 green thread 计数 | ncrt |
| all-asleep 死锁 panic | ncrt |
| `sync.Mutex`（标准库） | 标准库 + ncrt |
| `sleep`（timer yield） | ncrt |
| GC STW 窄化抢占 | ncrt（信号/APC） |

### v1 明确不包含

| 特性 | 原因 |
|---|---|
| channel / select | 无 case 驱动；语法和 lowering 成本高 |
| TCP I/O netpoller | 无 case 驱动；epoll/kqueue/IOCP 工作量大 |
| 文件 I/O 非阻塞包装 | 需要 io_uring 或相似技术 |
| 工作窃取调度 | 全局队列在 v1 场景足够 |
| 异步抢占（通用） | 合作式 yield 在 v1 可接受 |
| 动态栈增长 | 实现复杂且无 case 证明必要性 |
| 可观测性 / debug 基础设施 | 无 case 驱动 |
| per-P 内存分配缓存 | 先通后优 |

## 后续方向（v2 / case 驱动）

- **channel + select**：标准库 `chan.Chan[T]` + 编译器 `select` 构造
- **TCP netpoller**：epoll/kqueue/IOCP 事件循环寄生在 worker 中
- **工作窃取**：本地队列 + 偷取，降低全局队列锁竞争
- **动态栈增长**：达到风险监控范围
- **通用异步抢占**：信号驱动的抢占式调度，消除热循环不 yield 问题
