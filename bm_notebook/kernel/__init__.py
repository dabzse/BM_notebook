"""Jupyter kernel management and Qt-threaded execution bridge."""

from .manager import KernelBridge, KernelSpecInfo, discover_kernelspecs

__all__ = [
    "KernelBridge",
    "KernelSpecInfo",
    "discover_kernelspecs",
]
