# NC 编译器 — 原则

> 本文件只记录原则，不记录具体问题清单；具体问题由 case / worklog / issue 推动。

- **case 驱动架构**。每个 case 逼出一个编译器能力，不提前设计未用到的能力。
- **先通后优**。链路未通之前不优化，链路一旦通，即刻自省。
- **多 pass，各司其职，不跨界**。每个 pass 只做一件事。可有多 pass，不可有一 pass 做两事。
- 动手或者做计划之前，要先阅读 design.md worklog.md
- 更新 worklog 的时机：工作时，仅用 append 方式写，我预备做什么，成功与否。
- 更新 design.md 的时机：我预备做什么新feature（design.md中没有的），做完之后，检查一遍 design.md 是否和实现一致