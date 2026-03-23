"""
bluetooth_admin.py
------------------
Background Bluetooth discovery (PyBluez), inspired by the project snippet.

When exactly one configured device appears in scan results (match by MAC preferred,
or exact Bluetooth friendly name), sets a threading.Event for the admin TUIO flow.

Optional: install pybluez / pybluez2. If import fails, use config admin_bluetooth_force
for development.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

try:
    import bluetooth  # type: ignore
except ImportError:
    bluetooth = None  # type: ignore


def _normalize_mac(addr: str) -> str:
    return addr.strip().lower().replace("-", ":")


class BluetoothAdminPresence:
    """
    Poll discover_devices() in a daemon thread.

    * If ``mac`` is set: only that address unlocks admin (normalized, exact).
    * Else if ``name`` is set: only a device whose friendly name matches exactly
      (case-insensitive) unlocks admin — not substring, not “any of several”.
    * If neither is set (and not ``force_connected``), admin via Bluetooth stays locked.
    """

    def __init__(
        self,
        *,
        mac: str = "",
        name: str = "",
        scan_duration: int = 6,
        poll_interval: float = 3.0,
        ttl_seconds: float = 45.0,
        force_connected: bool = False,
        on_log: Callable[[str], None] | None = None,
    ):
        self._mac = _normalize_mac(mac) if mac else ""
        self._name = (name or "").strip().lower()
        self._scan_duration = max(2, int(scan_duration))
        self._poll_interval = max(1.0, float(poll_interval))
        self._ttl = max(5.0, float(ttl_seconds))
        self._force = bool(force_connected)
        self._on_log = on_log

        self.connected = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_seen: float = 0.0
        self._warned_no_identity = False

    def _log(self, msg: str) -> None:
        if self._on_log:
            self._on_log(msg)
        else:
            print(msg)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if bluetooth is None:
            self._log(
                "[BluetoothAdmin] PyBluez not installed — "
                "set admin_bluetooth_force=true in config.json for testing."
            )
            if self._force:
                self.connected.set()
            return
        if (
            not self._force
            and bluetooth is not None
            and not self._mac
            and not self._name
            and not self._warned_no_identity
        ):
            self._warned_no_identity = True
            self._log(
                "[BluetoothAdmin] Set admin_bluetooth_mac or admin_bluetooth_name "
                "in config.json to allow exactly one device to unlock admin."
            )
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self.connected.clear()

    def _match(self, addr: str, name: str | None) -> bool:
        addr_n = _normalize_mac(str(addr))
        if self._mac:
            return addr_n == self._mac
        if self._name:
            n = (name or "").strip().lower()
            return n == self._name
        return False

    def _run(self) -> None:
        while not self._stop.is_set():
            if self._force:
                self.connected.set()
                time.sleep(self._poll_interval)
                continue

            try:
                devices = bluetooth.discover_devices(  # type: ignore[union-attr]
                    duration=self._scan_duration,
                    lookup_names=True,
                )
                found = False
                for item in devices:
                    addr, name = None, None
                    if isinstance(item, tuple) and len(item) >= 1:
                        addr = item[0]
                        name = item[1] if len(item) > 1 else None
                    elif isinstance(item, str):
                        addr = item
                    if addr is None:
                        continue
                    if self._match(str(addr), name if isinstance(name, str) else None):
                        found = True
                        break
                now = time.monotonic()
                if found:
                    self._last_seen = now
                    self.connected.set()
                elif now - self._last_seen > self._ttl:
                    self.connected.clear()
            except Exception as exc:
                self._log(f"[BluetoothAdmin] Scan error: {exc}")
                if not self._force:
                    self.connected.clear()

            time.sleep(self._poll_interval)
