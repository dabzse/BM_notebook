"""Cross-platform PyInstaller build and archive packaging script for BM Notebook."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "BM-Notebook"


def _default_platform_slug() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    arch_map = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    arch = arch_map.get(machine, machine)
    if system == "darwin":
        return f"macos-{arch}"
    return f"{system}-{arch}"


def _binary_path(dist_dir: Path) -> Path:
    system = platform.system()
    if system == "Windows":
        return dist_dir / APP_NAME / f"{APP_NAME}.exe"
    if system == "Darwin":
        return dist_dir / f"{APP_NAME}.app" / "Contents" / "MacOS" / APP_NAME
    return dist_dir / APP_NAME / APP_NAME


def _run_pyinstaller(dist_dir: Path, work_dir: Path) -> None:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name",
        APP_NAME,
        "--workpath",
        str(work_dir),
        "--distpath",
        str(dist_dir),
        "--specpath",
        str(work_dir),
        "--add-data",
        f"{ROOT / 'examples'}{os.pathsep}examples",
        "--collect-submodules",
        "ipykernel",
        "--collect-submodules",
        "jupyter_client",
        "--collect-submodules",
        "zmq",
        "--collect-submodules",
        "pygments",
        "--hidden-import",
        "ipykernel.kernelapp",
        "--hidden-import",
        "ipykernel_launcher",
        str(ROOT / "bm_notebook" / "__main__.py"),
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)  # noqa: S603


def _copy_extras(bundle_dir: Path, include_examples: bool = True) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("LICENSE", "README.md", "README_hu.md"):
        src = ROOT / filename
        if src.is_file():
            shutil.copy2(src, bundle_dir / filename)
    if not include_examples:
        return
    examples_src = ROOT / "examples"
    examples_dst = bundle_dir / "examples"
    if examples_src.is_dir() and not examples_dst.exists():
        shutil.copytree(examples_src, examples_dst)


def _smoke_test_binary(binary: Path) -> None:
    if not binary.is_file():
        msg = f"Built executable not found: {binary}"
        raise FileNotFoundError(msg)
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["QT_QPA_PLATFORMTHEME"] = ""
    subprocess.run([str(binary), "--help"], env=env, check=True)  # noqa: S603


def _package_archive(dist_dir: Path, out_dir: Path, slug: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    system = platform.system()

    if system == "Darwin":
        archive_path = out_dir / f"{APP_NAME}-{slug}.zip"
        app_bundle = dist_dir / f"{APP_NAME}.app"
        ditto_bin = shutil.which("ditto") or "/usr/bin/ditto"
        subprocess.run(  # noqa: S603
            [ditto_bin, "-c", "-k", "--sequesterRsrc", "--keepParent", str(app_bundle), str(archive_path)],
            check=True,
        )
        return archive_path

    if system == "Windows":
        base_name = out_dir / f"{APP_NAME}-{slug}"
        produced = shutil.make_archive(str(base_name), "zip", root_dir=dist_dir, base_dir=APP_NAME)
        return Path(produced)

    archive_path = out_dir / f"{APP_NAME}-{slug}.tar.gz"
    bundle_dir = dist_dir / APP_NAME
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(bundle_dir, arcname=APP_NAME)
    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build standalone BM Notebook release archive.")
    parser.add_argument(
        "--platform-slug",
        default=_default_platform_slug(),
        help="Target archive suffix (e.g. linux-x86_64, windows-x86_64, macos-arm64).",
    )
    args = parser.parse_args()

    dist_dir = ROOT / "dist"
    work_dir = ROOT / "build" / "pyinstaller"
    out_dir = ROOT / "release-assets"

    shutil.rmtree(dist_dir, ignore_errors=True)
    shutil.rmtree(work_dir, ignore_errors=True)

    _run_pyinstaller(dist_dir, work_dir)
    if platform.system() == "Darwin":
        _copy_extras(dist_dir / f"{APP_NAME}.app" / "Contents" / "Resources", include_examples=False)
    else:
        _copy_extras(dist_dir / APP_NAME)
    _smoke_test_binary(_binary_path(dist_dir))
    archive = _package_archive(dist_dir, out_dir, args.platform_slug)
    print(f"Created release archive: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
