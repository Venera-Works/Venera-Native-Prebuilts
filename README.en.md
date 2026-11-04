# Venera-Native-Prebuilts

[中文](README.md)

Builds and releases the `rhttp 0.15.1` native libraries used by [Venera-Plus](https://github.com/Venera-Works/Venera-Plus). Application builds use Cargokit to download artifacts by source hash and verify their Ed25519 signatures. Missing or invalid artifacts fail instead of compiling rhttp locally.

`rhttp/lock.json` pins the source archive SHA-256, Flutter 3.41.4, Rust 1.85.1, FRB 2.11.1, Android NDK 28.0.13004108, and minimum API 21. `rhttp/cargokit.yaml` pins the public key, release URL, and `cargo --locked` arguments.

## Build platforms

| Build environment | Rust targets | Native files |
|---|---|---|
| Ubuntu 22.04 / Android | `armv7-linux-androideabi`, `aarch64-linux-android`, `i686-linux-android`, `x86_64-linux-android` | `librhttp.so` |
| Windows 2025 / x64 | `x86_64-pc-windows-msvc` | `rhttp.dll`, `rhttp.dll.lib` |
| Ubuntu 22.04 / x64 | `x86_64-unknown-linux-gnu` | `librhttp.so` |
| Ubuntu 22.04 ARM64 | `aarch64-unknown-linux-gnu` | `librhttp.so` |
| macOS 15 / Xcode 16.4 | `x86_64-apple-darwin`, `aarch64-apple-darwin`, `aarch64-apple-ios`, `aarch64-apple-ios-sim`, `x86_64-apple-ios` | `librhttp.a` |

Release filenames are `<target>_<native filename>`, each accompanied by a `.sig`. A complete release contains 13 binaries for 12 targets, 13 signature files, `LICENSE`, and `LICENSE-cargokit`. Android x86 supports Debug smoke builds.

## Enable CI

Configure the repository Actions Secret `RHTTP_PREBUILT_PRIVATE_KEY`. It must contain a 64-byte Ed25519 private key encoded as 128 hexadecimal characters and match the public key in `rhttp/cargokit.yaml`.

The current local key is stored in `.git/rhttp-prebuilt-private-key`, outside version control. From the repository root, this PowerShell pipeline configures the Secret without printing the key:

```powershell
Get-Content -Raw .git/rhttp-prebuilt-private-key |
  gh secret set RHTTP_PREBUILT_PRIVATE_KEY --repo Venera-Works/Venera-Native-Prebuilts
```

After pushing to `main`, changes to source configuration, build tools, or the workflow trigger precompilation. The `预编译 rhttp 原生二进制` workflow can also be dispatched manually. Five build jobs compile, sign, and upload Workflow Artifacts; only the final publishing job has `contents: write` permission.

Once every platform succeeds, publishing checks that all files exist, binaries are nonempty, and signatures contain 64 bytes. It uploads to a draft Release and publishes only after every upload succeeds. The compiler verifies each signature when generating it. Published releases are not overwritten; an incomplete draft can be completed by rerunning. One concurrency group prevents branches from publishing the same source hash simultaneously.

## Build one platform locally

Install FVM, Python 3.9+, and the platform's native build tools. Prepare the source from the repository root. The preparation script verifies the downloaded archive and retains the upstream tool dependency lock.

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

For Android, also pass `--android-sdk-location`, `--android-ndk-version 28.0.13004108`, and `--android-min-sdk-version 21`. Repeat `--target` to select multiple architectures. Apple builds require Xcode 16.4. Run from the preparation script's `tool_dir` so Cargokit can locate the Rust version lock at the repository root.

Run the following command from the repository root to check the complete platform set. After building only one platform, it reports the other targets as missing:

```powershell
python scripts/prepare_rhttp.py --check-output dist
```

## Upgrade and integrate

1. Update `rhttp/lock.json`, `rhttp/cargokit.yaml`, and the corresponding SDK, Rust, and workflow configuration.
2. Verify the upstream tool dependency lock and native builds using the pinned SDK and `pub.dev`.
3. Synchronize `lock.json` and `cargokit.yaml` with the application's `native/prebuilts/rhttp/`, and update the corresponding upstream Cargokit source digests in the application's preparation script.
4. Publish every target in `precompiled_<crateHash>` before building the application. Source, Cargo lock, build arguments, and public-key changes alter the hash.

The application runs `dart tool/prepare_rhttp_prebuilt.dart` after `flutter pub get` to configure the resolved package and disable rhttp source fallback. Local application development uses a project-specific `.pub-cache`; see its build guide. The main repository continues to build and sign application packages.
