# Venera-Native-Prebuilts

[English](README.en.md)

为 [Venera-Plus](https://github.com/Venera-Works/Venera-Plus) 预编译并发布 `rhttp 0.15.1` 原生库。应用构建通过 Cargokit 按源码 hash 下载产物并验证 Ed25519 签名，缺包或验签失败时停止，不再现场编译 rhttp。

`rhttp/lock.json` 固定源归档 SHA-256、Dart 3.11.1（对应应用 Flutter 3.41.4）、Rust 1.85.1、FRB 2.11.1、Android NDK 28.0.13004108 和最低 API 21。`rhttp/cargokit.yaml` 固定公钥、发布地址及 `cargo --locked` 参数。

`rhttp/Cargo.toml` 与 `rhttp/Cargo.lock` 将 Rust 桥接运行库及宏固定到上游提交 [`d59f05b6b0da3606933385f80cbd9e21cc35b59c`](https://github.com/fzyzcjy/flutter_rust_bridge/commit/d59f05b6b0da3606933385f80cbd9e21cc35b59c)，保持 `2.11.1` 版本，修复取消请求后迟到的 Dart 回调触发原生崩溃。准备脚本解压并验证上游包后应用这两份文件，再计算新的源码 hash；其余依赖沿用原锁定版本。

## 构建平台

| 构建环境 | Rust targets | 原生文件 |
|---|---|---|
| Ubuntu 22.04 / Android | `armv7-linux-androideabi`、`aarch64-linux-android`、`i686-linux-android`、`x86_64-linux-android` | `librhttp.so` |
| Windows 2025 / x64 | `x86_64-pc-windows-msvc` | `rhttp.dll`、`rhttp.dll.lib` |
| Ubuntu 22.04 / x64 | `x86_64-unknown-linux-gnu` | `librhttp.so` |
| Ubuntu 22.04 ARM64 | `aarch64-unknown-linux-gnu` | `librhttp.so` |
| macOS 15 / Xcode 16.4 | `x86_64-apple-darwin`、`aarch64-apple-darwin`、`aarch64-apple-ios`、`aarch64-apple-ios-sim`、`x86_64-apple-ios` | `librhttp.a` |

发布文件名为 `<target>_<原生文件名>`，每份文件配套一个同名 `.sig`。完整发布包含 12 个目标的 13 个二进制文件、13 个签名文件，以及 `LICENSE`、`LICENSE-cargokit`。Android x86 用于 Debug 冒烟构建。

## 首次启用 CI

将签名私钥配置为本仓库的 Actions Secret `RHTTP_PREBUILT_PRIVATE_KEY`。私钥格式为 64 字节、128 个十六进制字符，必须与 `rhttp/cargokit.yaml` 中的公钥配对。

当前本地私钥保存在 `.git/rhttp-prebuilt-private-key`，不进入版本控制。可在仓库根目录通过 PowerShell 管道配置 Secret，无需打印私钥：

```powershell
Get-Content -Raw .git/rhttp-prebuilt-private-key |
  gh secret set RHTTP_PREBUILT_PRIVATE_KEY --repo Venera-Works/Venera-Native-Prebuilts
```

将代码推送到 `main` 后，相关源码配置、构建工具或工作流变化会触发预编译；也可手动运行 `预编译 rhttp 原生二进制`。五个平台任务只编译、签名并上传 Workflow Artifacts，只有最终发布任务具有 `contents: write` 权限。

CI 只安装锁定版本的独立 Dart SDK，并按运行器架构选择 x64 或 ARM64。原生预编译工具不需要 Flutter SDK；Flutter 3.41.4 stable 没有 Linux ARM64 发布包，因此不能在该运行器上使用 Flutter 安装步骤。SDK 版本由准备脚本从 `rhttp/lock.json` 输出，五个平台使用同一配置。

发布任务在全部平台成功后检查文件是否齐全、二进制非空、签名文件为 64 字节，先上传至草稿 Release，全部上传成功后再公开。编译器在生成每份产物时验证其签名。公开发布不会被后续运行覆盖，未完成的草稿可以重跑补齐。所有运行使用同一并发组，避免不同分支同时发布相同源码 hash。

## 本地构建单个平台

需要 FVM、Python 3.9+ 以及对应平台的原生编译工具。先在仓库根目录准备源码；归档会下载并验 SHA-256，工具沿用上游自带的依赖锁。

```powershell
fvm use 3.41.4 --skip-pub-get
python scripts/prepare_rhttp.py
$env:PUB_HOSTED_URL = 'https://pub.dev'
$env:PRIVATE_KEY = (Get-Content -Raw .git/rhttp-prebuilt-private-key).Trim()
Set-Location build/rhttp/build/build_tool
fvm dart pub get --enforce-lockfile
fvm dart run bin/venera_precompile.dart `
  --manifest-dir ../../../package/rust `
  --output-dir ../../../../dist `
  --target x86_64-pc-windows-msvc
Remove-Item Env:PRIVATE_KEY
```

Android 构建额外传入 `--android-sdk-location`、`--android-ndk-version 28.0.13004108`、`--android-min-sdk-version 21`；`--target` 可重复指定。Apple 构建需使用 Xcode 16.4。准备脚本输出的 `tool_dir` 是必要工作目录，Cargokit 据此读取仓库根目录的 Rust 版本锁。

准备脚本保留上游完整的 Cargokit 目录，包括与 `build_tool` 同级的 `run_build_tool.sh`、`run_build_tool.cmd`，并设置 Unix 入口的可执行权限。Android 的 Rust 链接阶段通过这些入口调用 NDK Clang；`build_tool` 依赖这套相对目录结构。

Windows 本地交叉编译 Android 时，还需将 `FLUTTER_ROOT` 指向 FVM 的 Flutter SDK 目录（例如项目的 `.fvm/flutter_sdk`）；上游 `.cmd` 入口使用它定位 Dart。

在仓库根目录运行以下命令可检查全平台文件完整性；仅构建单个平台时，检查会报告尚缺的其他目标：

```powershell
python scripts/prepare_rhttp.py --check-output dist
```

## 升级与应用接入

1. 更新 `rhttp/lock.json`、`rhttp/cargokit.yaml`，以及对应的 SDK、Rust 和工作流配置。
2. 用固定 SDK 和 `pub.dev` 验证上游工具依赖锁及原生构建。
3. 将 `lock.json`、`cargokit.yaml`、`Cargo.toml` 与 `Cargo.lock` 同步到主项目的 `native/prebuilts/rhttp/`，并在升级 Cargokit 时更新主项目准备脚本中对应源文件的摘要。
4. 先发布本仓库全部目标的 `precompiled_<crateHash>`，再运行主项目构建。源码、Cargo 锁、构建参数或公钥变化会改变 hash。

主项目在 `flutter pub get` 之后运行 `dart tool/prepare_rhttp_prebuilt.dart`，配置已解析的包并禁用 rhttp 的源码回退。主项目本地开发使用项目专用 `.pub-cache`；详见其构建文档。正常应用包仍由主项目构建与签名。
