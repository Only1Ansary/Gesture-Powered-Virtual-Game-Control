"""
bluetooth_admin.py
------------------
Monitors whether the configured admin Bluetooth device is currently connected
to this Windows machine.

Detection strategy (first successful wins):
  1. WinRT  — instant, no scanning: checks `BluetoothDevice.connection_status`
               directly via `winrt-Windows.Devices.Bluetooth` (already installed
               with bleak).  Works for any classic-BT device paired to Windows.
  2. bleak  — BLE advertisement scan fallback for BLE-only devices.
  3. force_connected flag in config.json — bypass for development / demo.

Match by friendly name (admin_bluetooth_name) only:
  * name — case-insensitive match to the friendly name Windows shows for the paired device
  * admin_bluetooth_mac may remain in config for your records; it is not used for unlock.

NOTE:
  BLE devices often rotate their MAC for privacy.  For BLE-only devices use
  name matching, or set admin_bluetooth_force=true while developing.
"""

from __future__ import annotations

import asyncio
import threading
import time
import winreg
from typing import Callable


def _normalize_mac(addr: str) -> str:
    return addr.strip().lower().replace("-", ":").replace("_", ":")


def _mac_to_uint64(mac: str) -> int:
    """Convert "7c:03:ab:2a:0c:ce" → int for WinRT BluetoothDevice lookup."""
    return int(mac.replace(":", "").replace("-", ""), 16)


def _registry_paired_devices() -> dict[str, str]:
    """
    Return {normalized_mac: friendly_name} for all devices in the Windows
    Bluetooth device registry hive.  Never raises — returns {} on any error.
    """
    result: dict[str, str] = {}
    reg_path = r"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices"
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
        idx = 0
        while True:
            try:
                sub_name = winreg.EnumKey(key, idx)
                mac = ":".join(sub_name[j:j+2] for j in range(0, 12, 2)).lower()
                sub = winreg.OpenKey(key, sub_name)
                try:
                    raw, _ = winreg.QueryValueEx(sub, "Name")
                    name = (
                        raw.rstrip(b"\x00").decode("utf-8", errors="replace")
                        if isinstance(raw, bytes) else str(raw)
                    )
                except FileNotFoundError:
                    name = ""
                winreg.CloseKey(sub)
                result[mac] = name
                idx += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except Exception:
        pass
    return result


# ── optional backends ──────────────────────────────────────────────────────────

try:
    from winrt.windows.devices.bluetooth import (   # type: ignore
        BluetoothDevice, BluetoothConnectionStatus,
    )
    _WINRT_OK = True
except ImportError:
    BluetoothDevice = None                          # type: ignore[assignment,misc]
    BluetoothConnectionStatus = None                # type: ignore[assignment]
    _WINRT_OK = False

try:
    from bleak import BleakScanner                  # type: ignore
    _BLEAK_OK = True
except ImportError:
    BleakScanner = None                             # type: ignore[assignment,misc]
    _BLEAK_OK = False

try:
    import bluetooth as _pybluez                   # type: ignore
    _PYBLUEZ_OK = True
except ImportError:
    _pybluez = None                                # type: ignore[assignment]
    _PYBLUEZ_OK = False


class BluetoothAdminPresence:
    """
    Poll for the admin Bluetooth device in a daemon thread.

    ``connected`` (threading.Event) is SET while the device is connected/visible
    and CLEARED once it has been absent for more than ``ttl_seconds``.
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
        self._mac_config = _normalize_mac(mac) if mac else ""  # unused for unlock; kept for config parity
        self._name = (name or "").strip().lower()
        self._scan_duration = max(2, int(scan_duration))
        self._poll          = max(1.0, float(poll_interval))
        self._ttl           = max(5.0, float(ttl_seconds))
        self._force         = bool(force_connected)
        self._on_log        = on_log
        self._resolved_mac = ""  # filled from registry when matching by name (WinRT)

        self.connected      = threading.Event()
        self._stop          = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_seen: float = 0.0
        self._matched_display_name = ""

        if _WINRT_OK:
            backend = "WinRT (instant connection check — no scan needed)"
        elif _PYBLUEZ_OK:
            backend = "PyBluez (classic BT scan)"
        elif _BLEAK_OK:
            backend = "bleak (BLE advertisement scan — fallback)"
        else:
            backend = "NONE"

        self._log(f"[BluetoothAdmin] Backend: {backend}")
        if force_connected:
            self._log("[BluetoothAdmin] force_connected=true — admin always unlocked.")
        elif self._mac_config and not self._name:
            self._log(
                "[BluetoothAdmin] admin_bluetooth_mac is set but ignored — "
                "set admin_bluetooth_name to the device name shown in Windows."
            )

    # ── public API ─────────────────────────────────────────────────────────────

    @property
    def matched_device_name(self) -> str:
        """Friendly name of the device when connected (WinRT); may be empty."""
        return self._matched_display_name

    def start(self) -> None:
        if self._force:
            self.connected.set()
            return
        if not _WINRT_OK and not _BLEAK_OK and not _PYBLUEZ_OK:
            self._log(
                "[BluetoothAdmin] No Bluetooth library available.\n"
                "  Run:  pip install bleak\n"
                "  Or set admin_bluetooth_force=true in config.json."
            )
            return
        if not self._name:
            self._log(
                "[BluetoothAdmin] No device name configured — set admin_bluetooth_name "
                "in config.json (MAC-only unlock is disabled)."
            )
            return

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="BtAdminScanner"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        self.connected.clear()

    # ── internal ───────────────────────────────────────────────────────────────

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._poll_loop())
        finally:
            loop.close()

    async def _poll_loop(self) -> None:
        while not self._stop.is_set():
            if self._force:
                self.connected.set()
            else:
                found = await self._check_presence()
                self._update_state(found)

            elapsed = 0.0
            while elapsed < self._poll and not self._stop.is_set():
                await asyncio.sleep(0.5)
                elapsed += 0.5

    async def _check_presence(self) -> bool:
        """Try each backend in order; return True if the admin device is present."""
        # 1. WinRT instant connection check (best on Windows — no scan delay)
        if _WINRT_OK:
            result = await self._winrt_check()
            if result is not None:
                return result

        # 2. PyBluez classic scan
        if _PYBLUEZ_OK:
            return self._pybluez_scan()

        # 3. BLE advertisement scan via bleak
        if _BLEAK_OK:
            return await self._bleak_scan()

        return False

    # ── WinRT: instant paired-device connection check ──────────────────────────

    async def _winrt_check(self) -> bool | None:
        """
        Returns True/False if connection status could be determined,
        or None if the device wasn't found in the pairing database
        (falls through to the next backend).
        """
        try:
            target_mac = self._resolve_mac_from_name()
            if not target_mac:
                return None

            addr_int = _mac_to_uint64(target_mac)
            device = await BluetoothDevice.from_bluetooth_address_async(addr_int)
            if device is None:
                return None

            is_conn = (
                device.connection_status == BluetoothConnectionStatus.CONNECTED
            )
            try:
                nm = device.name
                self._matched_display_name = (str(nm) if nm else "").strip()
            except Exception:
                self._matched_display_name = ""
            if not is_conn:
                self._matched_display_name = ""
            return is_conn

        except Exception as exc:
            self._log(f"[BluetoothAdmin] WinRT check error: {exc}")
            return None

    def _resolve_mac_from_name(self) -> str:
        """Bluetooth address from registry using admin_bluetooth_name only (not config MAC)."""
        if not self._name:
            return ""
        if self._resolved_mac:
            return self._resolved_mac
        paired = _registry_paired_devices()
        want = self._name.strip().lower()
        for mac, dev_name in paired.items():
            dn = dev_name.strip().lower()
            if dn and want in dn:
                self._resolved_mac = mac
                self._log(f"[BluetoothAdmin] Resolved name {self._name!r} -> {mac}")
                return mac
        self._resolved_mac = ""
        return ""

    # ── PyBluez: classic BT scan ───────────────────────────────────────────────

    def _pybluez_scan(self) -> bool:
        try:
            devices = _pybluez.discover_devices(   # type: ignore[union-attr]
                duration=self._scan_duration, lookup_names=True
            )
            for item in devices:
                addr = item[0] if isinstance(item, tuple) else str(item)
                dname = item[1] if isinstance(item, tuple) and len(item) > 1 else None
                if self._match_addr_name(addr, dname):
                    return True
        except Exception as exc:
            self._log(f"[BluetoothAdmin] PyBluez scan error: {exc}")
        return False

    # ── bleak: BLE advertisement scan ─────────────────────────────────────────

    async def _bleak_scan(self) -> bool:
        try:
            devices = await BleakScanner.discover(   # type: ignore[union-attr]
                timeout=float(self._scan_duration), return_adv=False
            )
            for dev in devices:
                if self._match_addr_name(dev.address, dev.name):
                    return True
        except Exception as exc:
            self._log(f"[BluetoothAdmin] bleak scan error: {exc}")
        return False

    # ── shared helpers ─────────────────────────────────────────────────────────

    def _match_addr_name(self, addr: str | None, name: str | None) -> bool:
        if self._name and name:
            nn = name.strip().lower()
            return self._name in nn if nn else False
        return False

    def _update_state(self, found: bool) -> None:
        now = time.monotonic()
        if found:
            self._last_seen = now
            if not self.connected.is_set():
                label = self._matched_display_name or self._name or "device"
                self._log(f"[BluetoothAdmin] Connected — admin unlocked ({label}).")
            self.connected.set()
        elif now - self._last_seen > self._ttl:
            if self.connected.is_set():
                self._log("[BluetoothAdmin] Device disconnected — admin locked.")
            self.connected.clear()
            self._matched_display_name = ""

    def _log(self, msg: str) -> None:
        if self._on_log:
            self._on_log(msg)
        else:
            print(msg)
