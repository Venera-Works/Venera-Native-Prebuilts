# rhttp 原生依赖锁定

本轮更新覆盖应用仓库剩余的 10 项 Dependabot 告警，锁定以下安全修复版本：

| 依赖 | 锁定版本 | 处理内容 |
|---|---|---|
| `bytes` | `1.11.1` | 修复 `BytesMut::reserve` 整数溢出 |
| `rustls` | `0.23.46` | 修复 TLS 1.3 握手边界、证书解压、会话 Debug 机密暴露及密钥交换预测问题 |
| `rustls-webpki` | `0.103.14` | 修复 CRL 解析与匹配、通配符及 URI 名称约束；满足 rustls 的 `^0.103.14` 约束 |
| `time` | `0.3.47` | 限制 RFC 2822 解析递归，避免栈耗尽 |
| `quinn-proto` | `0.11.19` | 保留 QUIC 解析、乱序流内存占用、Retry token 和流数量限制修复 |
| `quinn-udp` | `0.5.16` | 保留截断 UDP 数据报接收死循环修复 |
| `rand` | `0.10.3` | 保留已更新的随机数依赖 |

公告依据：[bytes](https://github.com/advisories/GHSA-434x-w66g-qw3r)、[time](https://github.com/advisories/GHSA-r6v5-fh4h-64xc)、[rustls](https://github.com/rustls/rustls/security/advisories)、[webpki](https://github.com/rustls/webpki/security/advisories)。

## time 与 Rust 工具链

`time 0.3.47` 声明最低 Rust 版本为 `1.88.0`，因此 `rust-toolchain.toml`、`rhttp/lock.json`、Cargo 清单、Cargokit 配置和五个平台 CI 统一使用 Rust `1.88.0`。`time-core 0.1.8`、`time-macros 0.2.27` 和 `num-conv 0.2.2` 随之更新。

继续使用 `rhttp 0.15.1`、`reqwest 0.12.25`、Flutter `3.41.4`、Dart `3.11.1`、Android NDK `28.0.13004108` 和最低 API 21。FRB 运行库及宏保持 `2.11.1`，固定上游提交 `d59f05b6b0da3606933385f80cbd9e21cc35b59c`，包含取消后的迟到回调修复。

Rust `1.88.0` 的 `cargo metadata --locked` 解析成功，共 242 个包；已声明的最低 Rust 版本均不高于 `1.88.0`。

## 发布与应用接入

本锁文件及构建配置对应 [`precompiled_3aea817bfb329ec326ef4561451cab83`](https://github.com/Venera-Works/Venera-Native-Prebuilts/releases/tag/precompiled_3aea817bfb329ec326ef4561451cab83)。五个平台任务负责 12 个目标的编译和签名，发布任务检查 13 份二进制、13 份签名及 2 份许可证齐全后公开 Release。

发布完成并核验摘要和 Ed25519 签名后，将 `Cargo.toml`、`Cargo.lock`、`lock.json` 和 `cargokit.yaml` 同步到应用的 `native/prebuilts/rhttp/`。应用准备脚本计算出的 hash 必须与本 Release 一致。各平台构建结果见 [原生预编译工作流](https://github.com/Venera-Works/Venera-Native-Prebuilts/actions/workflows/prebuild-rhttp.yml)，消费端按对应平台验证取消回调及 HTTP/3。
