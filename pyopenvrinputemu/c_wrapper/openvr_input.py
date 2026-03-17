import ctypes
import json
import os
import os.path
import time
from uuid import uuid4

import openvr
from math import cos, sin


def get_hmd_id():
    vrsys = openvr.VRSystem()
    for i in range(openvr.k_unMaxTrackedDeviceCount):
        device_class = vrsys.getTrackedDeviceClass(i)
        if device_class == openvr.TrackedDeviceClass_HMD:
            return i


class VRInputSystem:
    def __init__(self, global_offset, global_rotation):
        dll = os.path.join(os.path.dirname(__file__), 'pyopenvr_emu_c_wrapper', 'x64', 'Release',
                           'pyopenvr_emu_c_wrapper.dll')

        self.global_offset = global_offset
        self.global_rotation = global_rotation

        vrinputemu = ctypes.cdll.LoadLibrary(dll)
        self.vrinputemu = vrinputemu
        cr = vrinputemu.create_connection
        cr.restype = ctypes.c_void_p
        emu = vrinputemu.create_connection()
        emu_p = ctypes.c_void_p(emu)
        self.emu_p = emu_p

        openvr.init(openvr.VRApplication_Background)
        self.vrsys = openvr.VRSystem()

        hmd_id = get_hmd_id()
        self.hmd_id = hmd_id

        poses_t = openvr.TrackedDevicePose_t * openvr.k_unMaxTrackedDeviceCount
        self.poses = poses_t()

        set_pose = vrinputemu.set_virtual_device_pose
        set_pose.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_double,
                             ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
                             ]
        self.set_tracker_pose = set_pose

    def add_tracker(self, name=None):
        add_dev = self.vrinputemu.add_virtual_device
        add_dev.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        add_dev.restype = ctypes.c_uint32

        if name is None:
            name = uuid4()
        dev = add_dev(self.emu_p, ctypes.c_wchar_p(name))
        tracker = VirtualTracker(dev, name, self)
        return tracker

    def add_controller(self, name=None, role="left"):
        """Create a virtual device and set its controller role hint.

        Parameters
        ----------
        name : str or None
            Serial name for the virtual device.
        role : str
            'left' or 'right' — sets the ControllerRoleHint so Beat Saber
            recognises this device as a saber.
        """
        tracker = self.add_tracker(name)

        # Map role string to OpenVR enum value
        if role == "left":
            role_value = openvr.TrackedControllerRole_LeftHand   # 1
        else:
            role_value = openvr.TrackedControllerRole_RightHand  # 2

        # Give SteamVR a moment to register the new device
        time.sleep(0.3)

        # Find the device index by scanning for matching serial number
        device_index = self._find_device_by_serial(name or "")
        if device_index is not None:
            self._set_controller_role_override(device_index, name, role_value)
            print(f"[VRInputSystem] Device '{name}' (idx={device_index}) → "
                  f"role={'LEFT' if role == 'left' else 'RIGHT'}")
        else:
            print(f"[VRInputSystem] WARN: Could not find device '{name}' in SteamVR "
                  f"device list. Controller role NOT set.")

        return tracker

    def _find_device_by_serial(self, serial):
        """Scan all tracked devices and return the index whose serial matches."""
        for i in range(openvr.k_unMaxTrackedDeviceCount):
            dc = self.vrsys.getTrackedDeviceClass(i)
            if dc == openvr.TrackedDeviceClass_Invalid:
                continue
            try:
                dev_serial = self.vrsys.getStringTrackedDeviceProperty(
                    i, openvr.Prop_SerialNumber_String)
                if dev_serial == serial:
                    return i
            except Exception:
                continue
        return None

    def _set_controller_role_override(self, device_index, serial, role_value):
        """Write a per-device controller-role override into SteamVR settings.

        SteamVR reads per-device overrides from its steamvr.vrsettings file
        under sections named by the device serial.  We also try the
        VRSettings API for an immediate effect.
        """
        try:
            # Method 1: Use openvr VRSettings to write per-device section
            settings = openvr.VRSettings()
            section = f"driver_00vrinputemulator/devices/{serial}"
            # Try setting controller role hint
            settings.setInt32(section, "controllerRoleHint", role_value)
            print(f"[VRInputSystem] Set controllerRoleHint={role_value} via VRSettings")
        except Exception as e:
            print(f"[VRInputSystem] VRSettings method: {e}")

        try:
            # Method 2: Direct steamvr.vrsettings file modification
            self._write_vrsettings_override(serial, role_value)
        except Exception as e:
            print(f"[VRInputSystem] vrsettings file method: {e}")

    def _write_vrsettings_override(self, serial, role_value):
        """Append a controller-role override directly to steamvr.vrsettings."""
        # Find steamvr.vrsettings location
        config_path = None
        try:
            # Try reading from openvr runtime paths
            vrpaths_candidates = [
                os.path.expandvars(r"%LOCALAPPDATA%\openvr\openvrpaths.vrpath"),
            ]
            for p in vrpaths_candidates:
                if os.path.isfile(p):
                    with open(p, 'r') as f:
                        paths = json.load(f)
                    config_dirs = paths.get("config", [])
                    for cd in config_dirs:
                        candidate = os.path.join(cd, "steamvr.vrsettings")
                        if os.path.isfile(candidate):
                            config_path = candidate
                            break
                if config_path:
                    break
        except Exception:
            pass

        if not config_path:
            print("[VRInputSystem] Could not locate steamvr.vrsettings")
            return

        # Read existing settings
        with open(config_path, 'r') as f:
            settings = json.load(f)

        # Add per-device override — SteamVR uses the device serial as key
        # in a "trackers" section to set controller role hints
        trackers = settings.setdefault("trackers", {})
        # Format: "/devices/00vrinputemulator/<serial>" = "TrackedControllerRole_LeftHand" etc
        device_path = f"/devices/00vrinputemulator/{serial}"
        if role_value == openvr.TrackedControllerRole_LeftHand:
            trackers[device_path] = "TrackedControllerRole_LeftHand"
        else:
            trackers[device_path] = "TrackedControllerRole_RightHand"

        with open(config_path, 'w') as f:
            json.dump(settings, f, indent=3)

        print(f"[VRInputSystem] Wrote role override to {config_path}")

    def tracker_count(self):
        return self.vrinputemu.get_virtual_device_count(self.emu_p)

    def get_hmd_quaternion(self):
        self.vrsys.getDeviceToAbsoluteTrackingPose(openvr.TrackingUniverseRawAndUncalibrated, 0, len(self.poses),
                                                   self.poses,)
        pose = self.poses[self.hmd_id]
        m = pose.mDeviceToAbsoluteTracking.m

        qw = (1 + m[0][0] + m[1][1] + m[2][2]) ** 0.5 / 2
        qx = (m[1][2] - m[2][1]) / (4 * qw)
        qy = (m[2][0] - m[0][2]) / (4 * qw)
        qz = (m[0][1] - m[1][0]) / (4 * qw)
        return qw, qx, -qy, qz

    def update_tracker(self, device_id, x, y, z, qw, qx, qy, qz):

        # rotate around z
        q = self.global_rotation[2]
        z = z
        x = x * cos(q) - y* sin(q)
        y = x* sin (q) + y*cos(q)

        # rotate around y
        q = self.global_rotation[1]
        z = z*cos(q) - x*sin(q)
        x = z*sin (q) + x*cos (q)

        # rotate around x
        q = self.global_rotation[0]
        y = y*cos (q) - z*sin (q)
        z = y*sin(q) + z*cos (q)

        x += self.global_offset[0]
        y += self.global_offset[1]
        z += self.global_offset[2]

        self.set_tracker_pose(self.emu_p, device_id, x, y, z, qx, qy, qz, qw)

class VirtualTracker():
    def __init__(self, dev, name, inputemu):
        self.x = 0
        self.y = 0
        self.z = 0

        self.device_id = dev
        self.name = name
        self.inputemu = inputemu

    def update(self, x ,y, z):
        self.x = x
        self.y = y
        self.z = z
        qw, qx, qy, qz = self.inputemu.get_hmd_quaternion()
        self.inputemu.update_tracker(self.device_id, x, y, z, qw, qx, qy, qz)