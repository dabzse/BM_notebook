"""Threaded Jupyter kernel bridge for PySide6 without blocking the UI thread."""

from __future__ import annotations

import ast
import contextlib
import json
import logging
import os
import queue
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jupyter_client
from jupyter_client.kernelspec import KernelSpecManager
from jupyter_core.paths import jupyter_data_dir
from PySide6.QtCore import QObject, Signal

from bm_notebook.model import CellOutput

_logger = logging.getLogger(__name__)


@dataclass
class KernelSpecInfo:
    name: str
    display_name: str
    language: str


@dataclass
class ExecutionTask:
    cell_id: str
    code: str
    removed_defs: list[str]


@dataclass
class _DrainState:
    ok: bool = True
    exec_count: int | None = None
    error_msg: str | None = None
    saw_idle: bool = False
    saw_reply: bool = False


def ensure_writable_jupyter_env() -> dict[str, str]:
    """Ensure Jupyter, IPython, and Matplotlib runtime dirs are writable."""
    base_tmp = Path(tempfile.gettempdir()) / "bm_notebook_runtime"
    env_updates: dict[str, str] = {}

    def _is_writable_dir(p: Path) -> bool:
        try:
            p.mkdir(parents=True, exist_ok=True)
            probe = p / ".bm_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError:
            return False
        else:
            return True

    home = Path.home()
    checks = {
        "JUPYTER_RUNTIME_DIR": home / ".local" / "share" / "jupyter" / "runtime",
        "JUPYTER_DATA_DIR": home / ".local" / "share" / "jupyter",
        "IPYTHONDIR": home / ".ipython",
        "MPLCONFIGDIR": home / ".config" / "matplotlib",
    }
    for var, default_dir in checks.items():
        current = os.environ.get(var)
        target = Path(current) if current else default_dir
        if not _is_writable_dir(target):
            fallback = base_tmp / var.lower()
            fallback.mkdir(parents=True, exist_ok=True)
            os.environ[var] = str(fallback)
            env_updates[var] = str(fallback)

    return env_updates


def _ensure_frozen_kernelspec(data_dir: Path) -> None:
    """Register an embedded Python kernelspec when running from a frozen bundle."""
    if not getattr(sys, "frozen", False):
        return
    kdir = data_dir / "kernels" / "bm-python"
    kdir.mkdir(parents=True, exist_ok=True)
    spec = {
        "argv": [sys.executable, "--bm-ipykernel", "-f", "{connection_file}"],
        "display_name": "Python (beépített)",
        "language": "python",
        "metadata": {"debugger": True},
    }
    (kdir / "kernel.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")


def discover_kernelspecs() -> list[KernelSpecInfo]:
    """Return available Jupyter kernelspecs on the machine."""
    ensure_writable_jupyter_env()
    _ensure_frozen_kernelspec(Path(jupyter_data_dir()))
    ksm = KernelSpecManager()
    specs: list[KernelSpecInfo] = []
    try:
        all_specs = ksm.get_all_specs()
    except Exception:
        all_specs = {}

    for name, payload in sorted(all_specs.items()):
        spec = payload.get("spec", {})
        specs.append(
            KernelSpecInfo(
                name=name,
                display_name=spec.get("display_name", name),
                language=spec.get("language", "python"),
            )
        )
    if not specs:
        specs.append(KernelSpecInfo(name="python3", display_name="Python 3", language="python"))
    return specs


_VAR_INSPECT_SNIPPET = """
import json as _bm_json
_bm_skip = {"In", "Out", "get_ipython", "exit", "quit", "open"}
_bm_vars = []
for _bm_k, _bm_v in list(globals().items()):
    if _bm_k.startswith("_") or _bm_k in _bm_skip:
        continue
    if type(_bm_v).__name__ == "module":
        continue
    _bm_t = type(_bm_v).__name__
    try:
        if hasattr(_bm_v, "shape"):
            _bm_preview = f"shape={getattr(_bm_v, 'shape')}"
        elif isinstance(_bm_v, (list, tuple, dict, set)):
            _bm_preview = f"len={len(_bm_v)} {repr(_bm_v)[:70]}"
        else:
            _bm_preview = repr(_bm_v)[:90]
    except Exception:
        _bm_preview = "<unprintable>"
    _bm_vars.append({"name": _bm_k, "type": _bm_t, "preview": _bm_preview})
_bm_vars.sort(key=lambda x: x["name"].lower())
_bm_inspect_json = _bm_json.dumps(_bm_vars[:200])
""".strip()


class KernelBridge(QObject):
    """Background worker managing a Jupyter kernel and streaming cell outputs."""

    kernel_started = Signal(str, str)  # kernel_name, language
    kernel_status = Signal(str)  # "starting" | "idle" | "busy" | "dead"
    kernel_error = Signal(str)
    cell_started = Signal(str)
    cell_output = Signal(str, object)  # cell_id, CellOutput
    cell_finished = Signal(str, bool, object, float, object)  # cell_id, ok, exec_count, ms, err
    batch_aborted = Signal(list)  # remaining cell_ids skipped due to upstream error
    completions_ready = Signal(str, int, list, int, int)  # cell_id, req_pos, matches, start, end
    variables_updated = Signal(list)  # list of dicts

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        ensure_writable_jupyter_env()
        self._cmd_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._cancel_event = threading.Event()
        self._stop_event = threading.Event()
        self._km: jupyter_client.KernelManager | None = None
        self._kc: Any = None
        self._kernel_name = "python3"
        self._kernel_language = "python"
        self._worker = threading.Thread(target=self._worker_loop, daemon=True, name="BMKernelWorker")
        self._worker.start()

    @property
    def kernel_name(self) -> str:
        return self._kernel_name

    @property
    def kernel_language(self) -> str:
        return self._kernel_language

    def start_kernel(self, kernel_name: str = "python3", language: str = "python") -> None:
        self._cancel_event.clear()
        self._cmd_queue.put(("start", (kernel_name, language)))

    def restart_kernel(self) -> None:
        self._cancel_event.set()
        self._cmd_queue.put(("restart", None))

    def interrupt_kernel(self) -> None:
        self._cancel_event.set()
        km = self._km
        if km is not None and km.is_alive():
            try:
                km.interrupt_kernel()
            except Exception as exc:
                self.kernel_error.emit(f"Interrupt failed: {exc}")

    def execute_batch(self, tasks: list[ExecutionTask]) -> None:
        if not tasks:
            return
        self._cancel_event.clear()
        self._cmd_queue.put(("execute_batch", tasks))

    def request_completions(self, cell_id: str, code: str, cursor_pos: int) -> None:
        self._cmd_queue.put(("complete", (cell_id, code, cursor_pos)))

    def refresh_variables(self) -> None:
        self._cmd_queue.put(("inspect_vars", None))

    def shutdown(self) -> None:
        self._cancel_event.set()
        self._stop_event.set()
        self._cmd_queue.put(("shutdown", None))
        self._worker.join(timeout=3.0)

    def _shutdown_current_kernel(self) -> None:
        if self._kc is not None:
            with contextlib.suppress(Exception):
                self._kc.stop_channels()
            self._kc = None
        if self._km is not None:
            with contextlib.suppress(Exception):
                self._km.shutdown_kernel(now=True)
            self._km = None

    def _start_kernel_sync(self, kernel_name: str, language: str) -> None:
        self._shutdown_current_kernel()
        self._kernel_name = kernel_name
        self._kernel_language = language
        self.kernel_status.emit("starting")
        try:
            env = os.environ.copy()
            env.update(ensure_writable_jupyter_env())
            km = jupyter_client.KernelManager(kernel_name=kernel_name)
            km.start_kernel(env=env)
            kc = km.client()
            kc.start_channels()
            kc.wait_for_ready(timeout=20)
            self._km = km
            self._kc = kc
            self._init_matplotlib_inline()
            self.kernel_started.emit(kernel_name, language)
            self.kernel_status.emit("idle")
            self.variables_updated.emit([])
        except Exception as exc:
            self._shutdown_current_kernel()
            self.kernel_status.emit("dead")
            self.kernel_error.emit(f"Failed to start kernel '{kernel_name}': {exc}")

    def _init_matplotlib_inline(self) -> None:
        if self._kc is None or self._kernel_language.lower() != "python":
            return
        init_code = (
            "try:\n"
            "    get_ipython().run_line_magic('matplotlib', 'inline')\n"
            "except Exception:\n"
            "    pass\n"
        )
        try:
            msg_id = self._kc.execute(init_code, silent=True, store_history=False)
            self._drain_until_idle(msg_id, emit_cell_id=None, timeout=5.0)
        except Exception as exc:
            _logger.debug("matplotlib inline init skipped: %s", exc)

    def _poll_shell_reply(
        self, kc: Any, msg_id: str
    ) -> tuple[bool, bool, int | None, str | None]:
        """Poll shell channel once for `msg_id`; returns (saw_reply, ok, exec_count, err)."""
        try:
            reply = kc.get_shell_msg(timeout=0.02)
        except queue.Empty:
            return False, True, None, None
        except Exception as exc:
            _logger.debug("Shell poll error: %s", exc)
            return False, True, None, None

        if reply.get("parent_header", {}).get("msg_id") != msg_id:
            return False, True, None, None

        content = reply.get("content", {})
        exec_count = content.get("execution_count")
        if content.get("status") != "ok":
            ename = content.get("ename", "Error")
            evalue = content.get("evalue", "")
            return True, False, exec_count, f"{ename}: {evalue}".strip(": ")
        return True, True, exec_count, None

    def _handle_iopub_message(
        self,
        msg: dict[str, Any],
        emit_cell_id: str | None,
    ) -> tuple[bool, bool, int | None, str | None]:
        """Process one iopub message; returns (saw_idle, ok, exec_count, err_msg)."""
        mtype = msg.get("msg_type")
        content = msg.get("content", {})

        if mtype == "status":
            return content.get("execution_state") == "idle", True, None, None
        if mtype == "stream" and emit_cell_id is not None:
            self.cell_output.emit(
                emit_cell_id,
                CellOutput(
                    output_type="stream",
                    name=content.get("name", "stdout"),
                    text=content.get("text", ""),
                ),
            )
        elif mtype in {"execute_result", "display_data"} and emit_cell_id is not None:
            raw_data = content.get("data", {})
            norm_data = {k: str(v) for k, v in raw_data.items()}
            self.cell_output.emit(
                emit_cell_id,
                CellOutput(output_type=mtype, data=norm_data),
            )
        elif mtype == "error":
            ename = content.get("ename", "Error")
            evalue = content.get("evalue", "")
            tb = list(content.get("traceback", []))
            err_msg = f"{ename}: {evalue}".strip(": ")
            if emit_cell_id is not None:
                self.cell_output.emit(
                    emit_cell_id,
                    CellOutput(output_type="error", ename=ename, evalue=evalue, traceback=tb),
                )
            return False, False, None, err_msg
        elif mtype == "execute_input":
            return False, True, content.get("execution_count"), None
        return False, True, None, None

    def _drain_until_idle(
        self,
        msg_id: str,
        emit_cell_id: str | None,
        timeout: float = 120.0,
    ) -> tuple[bool, int | None, str | None]:
        """Consume iopub + shell reply for a single execution."""
        kc = self._kc
        if kc is None:
            return False, None, "Kernel not running"

        state = _DrainState()
        deadline = time.monotonic() + timeout

        while not (state.saw_idle and state.saw_reply):
            if self._stop_event.is_set():
                return False, state.exec_count, "Shutdown requested"
            if not self._drain_step(kc, msg_id, emit_cell_id, deadline, state):
                return False, state.exec_count, "Execution timed out"

        return state.ok, state.exec_count, state.error_msg

    def _update_reply_state(self, kc: Any, msg_id: str, state: _DrainState) -> None:
        if state.saw_reply:
            return
        r_seen, r_ok, r_ec, r_err = self._poll_shell_reply(kc, msg_id)
        if not r_seen:
            return
        state.saw_reply = True
        if r_ec is not None:
            state.exec_count = r_ec
        if not r_ok:
            state.ok = False
            state.error_msg = state.error_msg or r_err

    def _drain_step(
        self,
        kc: Any,
        msg_id: str,
        emit_cell_id: str | None,
        deadline: float,
        state: _DrainState,
    ) -> bool:
        self._update_reply_state(kc, msg_id, state)

        msg = self._next_iopub_message(kc)
        if msg is None:
            return not (time.monotonic() > deadline and not state.saw_reply)
        if msg.get("parent_header", {}).get("msg_id") != msg_id:
            return True

        i_idle, i_ok, i_ec, i_err = self._handle_iopub_message(msg, emit_cell_id)
        state.saw_idle = state.saw_idle or i_idle
        if not i_ok:
            state.ok = False
            state.error_msg = i_err
        if state.exec_count is None and i_ec is not None:
            state.exec_count = i_ec
        return True

    @staticmethod
    def _next_iopub_message(kc: Any, timeout: float = 0.03) -> dict[str, Any] | None:
        try:
            return kc.get_iopub_msg(timeout=timeout)
        except queue.Empty:
            return None
        except Exception as exc:
            _logger.debug("IOPub poll error: %s", exc)
            return None

    def _cleanup_removed_defs(self, removed_defs: list[str]) -> None:
        if not removed_defs or self._kc is None or self._kernel_language.lower() != "python":
            return
        names_lit = json.dumps(removed_defs)
        code = (
            f"for _bm_rm in {names_lit}:\n"
            "    globals().pop(_bm_rm, None)\n"
            "globals().pop('_bm_rm', None)\n"
        )
        try:
            msg_id = self._kc.execute(code, silent=True, store_history=False)
            self._drain_until_idle(msg_id, emit_cell_id=None, timeout=5.0)
        except Exception as exc:
            _logger.debug("Removed-defs cleanup skipped: %s", exc)

    def _inspect_variables_sync(self) -> None:
        if self._kc is None or self._kernel_language.lower() != "python":
            return
        try:
            msg_id = self._kc.execute(
                _VAR_INSPECT_SNIPPET,
                silent=True,
                store_history=False,
                user_expressions={"vars": "_bm_inspect_json"},
            )
            vars_list = self._read_vars_reply(self._kc, msg_id)
            self._drain_iopub_nonblocking()
            self.variables_updated.emit(vars_list)
        except Exception as exc:
            _logger.debug("Variable inspection failed: %s", exc)

    @staticmethod
    def _read_vars_reply(kc: Any, msg_id: str) -> list[dict[str, str]]:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            try:
                reply = kc.get_shell_msg(timeout=0.05)
            except queue.Empty:
                continue
            if reply.get("parent_header", {}).get("msg_id") != msg_id:
                continue
            uexpr = reply.get("content", {}).get("user_expressions", {})
            val = uexpr.get("vars", {})
            if val.get("status") == "ok":
                raw_str = val.get("data", {}).get("text/plain", "")
                if raw_str.startswith(("'", '"')):
                    decoded = ast.literal_eval(raw_str)
                    return json.loads(decoded)
            return []
        return []

    def _drain_iopub_nonblocking(self) -> None:
        if self._kc is None:
            return
        drained = 0
        while self._next_iopub_message(self._kc, timeout=0.01) is not None:
            drained += 1
        if drained:
            _logger.debug("Drained %d leftover iopub messages", drained)

    def _execute_batch_sync(self, tasks: list[ExecutionTask]) -> None:
        if self._kc is None:
            self._start_kernel_sync(self._kernel_name, self._kernel_language)
        if self._kc is None:
            self.batch_aborted.emit([t.cell_id for t in tasks])
            return

        self.kernel_status.emit("busy")
        aborted_from: int | None = None

        for idx, task in enumerate(tasks):
            if self._cancel_event.is_set() or self._stop_event.is_set():
                aborted_from = idx
                break
            self._cleanup_removed_defs(task.removed_defs)
            self.cell_started.emit(task.cell_id)
            ok, exec_count, elapsed, err_msg = self._execute_single_task(task)
            self.cell_finished.emit(task.cell_id, ok, exec_count, elapsed, err_msg)
            if not ok:
                aborted_from = idx + 1
                break

        if aborted_from is not None and aborted_from < len(tasks):
            self.batch_aborted.emit([t.cell_id for t in tasks[aborted_from:]])

        self._inspect_variables_sync()
        self.kernel_status.emit("idle" if self._kc is not None else "dead")

    def _execute_single_task(
        self, task: ExecutionTask
    ) -> tuple[bool, int | None, float, str | None]:
        t0 = time.perf_counter()
        if not task.code.strip():
            return True, None, (time.perf_counter() - t0) * 1000.0, None
        try:
            msg_id = self._kc.execute(task.code, store_history=True)
            ok, exec_count, err_msg = self._drain_until_idle(
                msg_id, emit_cell_id=task.cell_id, timeout=300.0
            )
        except Exception as exc:
            ok, exec_count, err_msg = False, None, str(exc)
        return ok, exec_count, (time.perf_counter() - t0) * 1000.0, err_msg

    def _complete_sync(self, cell_id: str, code: str, cursor_pos: int) -> None:
        if self._kc is None:
            return
        try:
            msg_id = self._kc.complete(code, cursor_pos)
            deadline = time.monotonic() + 0.8
            while time.monotonic() < deadline:
                reply = self._next_complete_reply(self._kc)
                if reply is not None and reply.get("parent_header", {}).get("msg_id") == msg_id:
                    c = reply.get("content", {})
                    matches = list(c.get("matches", []))
                    cstart = int(c.get("cursor_start", cursor_pos))
                    cend = int(c.get("cursor_end", cursor_pos))
                    self.completions_ready.emit(cell_id, cursor_pos, matches, cstart, cend)
                    return
        except Exception as exc:
            _logger.debug("Completion failed: %s", exc)

    @staticmethod
    def _next_complete_reply(kc: Any) -> dict[str, Any] | None:
        try:
            return kc.get_shell_msg(timeout=0.03)
        except queue.Empty:
            return None

    def _handle_command(self, cmd: str, payload: Any) -> None:
        if cmd == "start":
            kname, lang = payload
            self._start_kernel_sync(kname, lang)
        elif cmd == "restart":
            self._start_kernel_sync(self._kernel_name, self._kernel_language)
        elif cmd == "execute_batch":
            self._execute_batch_sync(payload)
        elif cmd == "complete":
            cell_id, code, cursor_pos = payload
            self._complete_sync(cell_id, code, cursor_pos)
        elif cmd == "inspect_vars":
            self._inspect_variables_sync()

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                cmd, payload = self._cmd_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if cmd == "shutdown":
                self._shutdown_current_kernel()
                break
            self._handle_command(cmd, payload)
