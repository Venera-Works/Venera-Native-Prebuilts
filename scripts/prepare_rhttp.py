#!/usr/bin/env python3
"""
scripts/prepare_rhttp.py
Prepares upstream rhttp package and Cargokit build tool for precompiling binaries.

Capabilities:
- Downloads https://pub.dev/api/archives/rhttp-0.15.1.tar.gz
- Verifies SHA256 against rhttp/lock.json
- Safely extracts archive into build/package
- Copies rhttp/cargokit.yaml into build/package/rust/cargokit.yaml
- Copies upstream cargokit/build_tool to build/rhttp/build/build_tool
- Copies tool/build_rhttp.dart to build/rhttp/build/build_tool/bin/venera_precompile.dart
- Computes Cargokit CrateHash from manifest_dir
- Emits manifest_dir, tool_dir, crate_hash, release_tag, flutter_version, dart_version to stdout & GITHUB_OUTPUT
- Standalone integrity verification via --check-output <dist_dir>
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import urllib.request


EXPECTED_TARGETS = [
    ("armv7-linux-androideabi", ["armv7-linux-androideabi_librhttp.so"]),
    ("aarch64-linux-android", ["aarch64-linux-android_librhttp.so"]),
    ("i686-linux-android", ["i686-linux-android_librhttp.so"]),
    ("x86_64-linux-android", ["x86_64-linux-android_librhttp.so"]),
    (
        "x86_64-pc-windows-msvc",
        [
            "x86_64-pc-windows-msvc_rhttp.dll",
            "x86_64-pc-windows-msvc_rhttp.dll.lib",
        ],
    ),
    ("x86_64-unknown-linux-gnu", ["x86_64-unknown-linux-gnu_librhttp.so"]),
    ("aarch64-unknown-linux-gnu", ["aarch64-unknown-linux-gnu_librhttp.so"]),
    ("x86_64-apple-darwin", ["x86_64-apple-darwin_librhttp.a"]),
    ("aarch64-apple-darwin", ["aarch64-apple-darwin_librhttp.a"]),
    ("aarch64-apple-ios", ["aarch64-apple-ios_librhttp.a"]),
    ("aarch64-apple-ios-sim", ["aarch64-apple-ios-sim_librhttp.a"]),
    ("x86_64-apple-ios", ["x86_64-apple-ios_librhttp.a"]),
]

EXPECTED_LICENSES = ["LICENSE", "LICENSE-cargokit"]


def compute_crate_hash(manifest_dir: Path) -> str:
    """Computes Cargokit CrateHash exactly matching Cargokit's CrateHash.compute().

    Algorithm:
    1. Collect all files in `src/` (recursively), sorted by file path.
    2. Append Cargo.toml, Cargo.lock, build.rs, cargokit.yaml if they exist.
    3. For each file, read as text, split lines, and hash utf-8 bytes of each line.
    4. Truncate sha256 digest to first 16 bytes, hex-encoded.
    """
    src_dir = manifest_dir / "src"
    if not src_dir.is_dir():
        raise FileNotFoundError(f"Source directory not found: {src_dir}")

    files = sorted(
        [p for p in src_dir.rglob("*") if p.is_file()],
        key=lambda p: str(p.relative_to(manifest_dir)).replace("\\", "/"),
    )

    for extra in ["Cargo.toml", "Cargo.lock", "build.rs", "cargokit.yaml"]:
        extra_path = manifest_dir / extra
        if extra_path.is_file():
            files.append(extra_path)

    hasher = hashlib.sha256()
    for file_path in files:
        content = file_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            hasher.update(line.encode("utf-8"))

    return hasher.digest()[:16].hex()


def safe_extract_tar(archive_path: Path, dest_dir: Path) -> None:
    """Safely extracts tar archive preventing path traversal."""
    dest_path = dest_dir.resolve()
    dest_path.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive_path, "r:*") as tar:
        for member in tar.getmembers():
            target_path = (dest_path / member.name).resolve()
            if not target_path.is_relative_to(dest_path):
                raise ValueError(
                    f"Path traversal detected in archive member: {member.name}"
                )
            if member.isdir():
                target_path.mkdir(parents=True, exist_ok=True)
            elif member.isreg():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as source, target_path.open("wb") as output:
                    shutil.copyfileobj(source, output)
            else:
                raise ValueError(f"Unsupported archive member: {member.name}")


def check_output(dist_dir: Path) -> bool:
    """Verifies that all 12 targets (13 binaries, 13 signatures) and 2 license files exist and are valid."""
    dist_dir = dist_dir.resolve()
    print(f"Checking prebuilt artifacts in: {dist_dir}")
    if not dist_dir.is_dir():
        print(f"ERROR: Output directory does not exist: {dist_dir}", file=sys.stderr)
        return False

    missing = []
    invalid = []

    # Check target artifacts and signatures
    for triple, binaries in EXPECTED_TARGETS:
        for binary_name in binaries:
            bin_path = dist_dir / binary_name
            sig_path = dist_dir / f"{binary_name}.sig"

            if not bin_path.exists():
                missing.append(binary_name)
            elif bin_path.stat().st_size == 0:
                invalid.append(f"{binary_name} (empty file)")

            if not sig_path.exists():
                missing.append(f"{binary_name}.sig")
            elif sig_path.stat().st_size != 64:
                invalid.append(
                    f"{binary_name}.sig (expected 64 bytes, got {sig_path.stat().st_size})"
                )

    # Check license files
    for lic_name in EXPECTED_LICENSES:
        lic_path = dist_dir / lic_name
        if not lic_path.exists():
            missing.append(lic_name)
        elif lic_path.stat().st_size == 0:
            invalid.append(f"{lic_name} (empty file)")

    if missing:
        print("ERROR: Missing expected files:", file=sys.stderr)
        for item in missing:
            print(f"  - {item}", file=sys.stderr)

    if invalid:
        print("ERROR: Corrupted or invalid files:", file=sys.stderr)
        for item in invalid:
            print(f"  - {item}", file=sys.stderr)

    if missing or invalid:
        print(
            f"Integrity check FAILED: {len(missing)} missing, {len(invalid)} invalid files.",
            file=sys.stderr,
        )
        return False

    total_files = sum(len(bins) * 2 for _, bins in EXPECTED_TARGETS) + len(EXPECTED_LICENSES)
    print(
        f"Integrity check PASSED: all {len(EXPECTED_TARGETS)} targets "
        f"({total_files} files: 13 binaries, 13 signatures, 2 licenses) are present and valid."
    )
    return True


def prepare(repo_root: Path) -> dict:
    lock_file = repo_root / "rhttp" / "lock.json"
    if not lock_file.is_file():
        raise FileNotFoundError(f"Missing lock file: {lock_file}")

    with open(lock_file, "r", encoding="utf-8") as f:
        lock_data = json.load(f)

    package = lock_data["package"]
    version = lock_data["version"]
    expected_sha256 = lock_data["archiveSha256"]
    flutter_version = lock_data["flutterVersion"]
    dart_version = lock_data["dartVersion"]

    cache_dir = repo_root / "build" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    archive_path = cache_dir / f"{package}-{version}.tar.gz"

    archive_url = f"https://pub.dev/api/archives/{package}-{version}.tar.gz"

    # Download if not present or corrupt
    download_needed = True
    if archive_path.is_file():
        hasher = hashlib.sha256()
        with open(archive_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        if hasher.hexdigest().lower() == expected_sha256.lower():
            print(f"Using cached archive: {archive_path}")
            download_needed = False
        else:
            print("Cached archive checksum mismatch, re-downloading...")
            archive_path.unlink()

    if download_needed:
        print(f"Downloading {archive_url} -> {archive_path}")
        req = urllib.request.Request(
            archive_url,
            headers={"User-Agent": "Venera-Prebuilt-Prepare/1.0"},
        )
        with urllib.request.urlopen(req) as resp, open(archive_path, "wb") as out_file:
            shutil.copyfileobj(resp, out_file)

        # Verify checksum
        hasher = hashlib.sha256()
        with open(archive_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        actual_sha256 = hasher.hexdigest().lower()
        if actual_sha256 != expected_sha256.lower():
            archive_path.unlink(missing_ok=True)
            raise ValueError(
                f"Archive SHA256 mismatch!\nExpected: {expected_sha256}\nGot:      {actual_sha256}"
            )
        print("Archive SHA256 verified successfully.")

    # Unpack into build/package
    package_dir = repo_root / "build" / "package"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    print(f"Extracting package to: {package_dir}")
    safe_extract_tar(archive_path, package_dir)

    # Copy repo's rhttp/cargokit.yaml into build/package/rust/cargokit.yaml
    cargokit_yaml_src = repo_root / "rhttp" / "cargokit.yaml"
    manifest_dir = package_dir / "rust"

    if not cargokit_yaml_src.is_file():
        raise FileNotFoundError(f"Missing source cargokit.yaml at: {cargokit_yaml_src}")

    cargokit_yaml_dst = manifest_dir / "cargokit.yaml"
    print(f"Copying cargokit.yaml -> {cargokit_yaml_dst}")
    shutil.copy2(cargokit_yaml_src, cargokit_yaml_dst)

    # Copy upstream cargokit/build_tool to build/rhttp/build/build_tool
    upstream_build_tool = package_dir / "cargokit" / "build_tool"
    if not upstream_build_tool.is_dir():
        raise FileNotFoundError(
            f"Upstream cargokit build_tool not found at: {upstream_build_tool}"
        )

    tool_dir = repo_root / "build" / "rhttp" / "build" / "build_tool"
    if tool_dir.exists():
        shutil.rmtree(tool_dir)
    tool_dir.parent.mkdir(parents=True, exist_ok=True)
    print(f"Copying Cargokit build_tool -> {tool_dir}")
    shutil.copytree(upstream_build_tool, tool_dir)

    # Copy tool/build_rhttp.dart to tool_dir/bin/venera_precompile.dart
    venera_precompile_src = repo_root / "tool" / "build_rhttp.dart"
    if not venera_precompile_src.is_file():
        raise FileNotFoundError(
            f"Missing tool/build_rhttp.dart at: {venera_precompile_src}"
        )

    venera_precompile_dst = tool_dir / "bin" / "venera_precompile.dart"
    print(f"Installing precompiler entrypoint -> {venera_precompile_dst}")
    venera_precompile_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(venera_precompile_src, venera_precompile_dst)

    # Compute CrateHash
    crate_hash = compute_crate_hash(manifest_dir)
    release_tag = f"precompiled_{crate_hash}"

    info = {
        "manifest_dir": str(manifest_dir.resolve()),
        "tool_dir": str(tool_dir.resolve()),
        "crate_hash": crate_hash,
        "release_tag": release_tag,
        "flutter_version": flutter_version,
        "dart_version": dart_version,
    }

    print("--- Preparation Info ---")
    for k, v in info.items():
        print(f"{k}: {v}")
    print("------------------------")

    # Write GITHUB_OUTPUT if present
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            for k, v in info.items():
                f.write(f"{k}={v}\n")
        print(f"Written variables to GITHUB_OUTPUT ({github_output})")

    return info


def main():
    parser = argparse.ArgumentParser(
        description="Prepare rhttp source archive and build tool for precompilation"
    )
    parser.add_argument(
        "--check-output",
        metavar="DIR",
        help="Check integrity of built artifacts in specified directory without preparing",
    )
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Run preparation even if --check-output is specified",
    )

    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parent.parent

    if args.check_output and not args.prepare:
        success = check_output(Path(args.check_output))
        # If manifest_dir already prepared, also expose hash/tag
        manifest_dir = repo_root / "build" / "package" / "rust"
        if manifest_dir.is_dir() and (manifest_dir / "Cargo.toml").is_file():
            try:
                ch = compute_crate_hash(manifest_dir)
                tag = f"precompiled_{ch}"
                print(f"crate_hash: {ch}")
                print(f"release_tag: {tag}")
                github_output = os.environ.get("GITHUB_OUTPUT")
                if github_output:
                    with open(github_output, "a", encoding="utf-8") as f:
                        f.write(f"crate_hash={ch}\n")
                        f.write(f"release_tag={tag}\n")
            except Exception as e:
                print(f"Note: Could not compute crate_hash: {e}")
        sys.exit(0 if success else 1)

    info = prepare(repo_root)

    if args.check_output:
        success = check_output(Path(args.check_output))
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
