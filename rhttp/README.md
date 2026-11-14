`Cargo.lock` 中的 QUIC 安全补丁使用 `quinn-proto 0.11.19` 和 `quinn-udp 0.5.16`，分别覆盖 Retry token 导致的崩溃或内存耗尽、流数量限制绕过，以及 Apple 等平台截断 UDP 数据报后的接收死循环。公告要求的修补版本见 [RUSTSEC-2026-0524](https://rustsec.org/advisories/RUSTSEC-2026-0524.html)、[RUSTSEC-2026-0523](https://github.com/RustSec/advisory-db/blob/main/crates/quinn-proto/RUSTSEC-2026-0523.md) 和 [RUSTSEC-2026-0538](https://rustsec.org/advisories/RUSTSEC-2026-0538.html)。

两项升级声明 MSRV 1.85，新增传递依赖声明的 MSRV 最高为 1.85，配套工具链为 Rust 1.85.1。解析组合包含 `reqwest 0.12.25`、`quinn 0.11.9` 和 FRB `2.11.1`，桥接运行库及宏固定到 `d59f05b6b0da3606933385f80cbd9e21cc35b59c`。Cargo 1.85.1 的 `metadata --locked` 和依赖反向树解析通过，242 个解析包中已声明的 MSRV 均不高于 1.85.1。已核对三项 RustSec 公告的修补范围、源归档摘要和源码，平台编译与运行验证需在获得授权后执行。

按现有 Cargokit 算法，此锁文件对应 `precompiled_b42566ca820f81fe4492745317a6b164`。2026-11-14 核对时，最近正式发布仍为 `precompiled_b37067bdf33d83fb72c57f10cd16948b`，包含 `quinn-proto 0.11.13` 和 `quinn-udp 0.5.14`。应用修补需在新的签名预编译完整发布、消费端锁文件同步后生效。

后续发布与接入需按以下顺序执行，并另行取得发布授权。

1. 在本独立资源仓库发布本次锁文件改动。推送 `main` 的 `rhttp/**` 变更会触发现有 `预编译 rhttp 原生二进制` 工作流，使用已配置的签名密钥。
2. 确认 `precompiled_b42566ca820f81fe4492745317a6b164` 已公开，12 个目标的 13 份二进制、13 份签名和两份许可证齐全，并完成平台原生检查。
3. 将本目录的 `Cargo.lock` 同步到应用的 `native/prebuilts/rhttp/Cargo.lock`，核对两仓库的 `Cargo.toml`、`lock.json` 和 `cargokit.yaml` 一致。
4. 在应用专用 Pub 缓存中使用固定 FVM SDK 获取锁定依赖并运行 `fvm dart tool/prepare_rhttp_prebuilt.dart`，确认计算出的 hash 与已发布产物一致。应用构建和新二进制的回调、HTTP/3 验证按各自授权执行。

The QUIC security update locks `quinn-proto 0.11.19` and `quinn-udp 0.5.16` for the three advisories linked above. Both packages declare Rust 1.85 as their MSRV, and their new transitive dependencies declare MSRVs up to Rust 1.85. The resolved combination uses Rust 1.85.1, reqwest 0.12.25, quinn 0.11.9, and FRB 2.11.1 pinned to `d59f05b6b0da3606933385f80cbd9e21cc35b59c`. Cargo 1.85.1 resolved the locked metadata and reverse dependency trees successfully. All declared MSRVs among the 242 resolved packages are compatible with 1.85.1. Native compilation and runtime validation require subsequent authorization.

The resulting Cargokit release tag is `precompiled_b42566ca820f81fe4492745317a6b164`. On 2026-11-14, the latest public release was still `precompiled_b37067bdf33d83fb72c57f10cd16948b`, with the vulnerable QUIC versions. After publication is authorized, publish this source change through the existing workflow, verify all 28 assets for the 12 targets, and complete platform checks. Then copy `Cargo.lock` into the application's `native/prebuilts/rhttp/`, verify that the other three pin files match, and prepare the package with the fixed FVM SDK. Application builds and callback/HTTP/3 checks follow their respective authorization requirements.
