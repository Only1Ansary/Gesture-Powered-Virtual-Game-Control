#nullable disable
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Linq;
using System.Threading;
using System.Diagnostics;
using System.Text.Json;
using System.Text;
using System.Windows.Forms;
using Microsoft.Win32;
using static CircularMenu.Form1;

namespace FruitNinjaGame
{
    // ═══════════════════════════════════════════════════════════════════════════
    //  DATA MODELS
    // ═══════════════════════════════════════════════════════════════════════════

    public class UserProfile
    {
        public string Name { get; set; }
        public Color Bg { get; set; }
        public Color HeaderBg { get; set; }
        public Color Accent { get; set; }
        public Color Fg { get; set; }
        public Color Glow { get; set; }
        public string AvatarPath { get; set; }
        public string GifPath { get; set; }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    //  CONFIG
    // ═══════════════════════════════════════════════════════════════════════════

    public static class AppConfig
    {
        // Order matters: BaseDir is read by LoadConfig(), so it must be initialised first.
        public static readonly string BaseDir = AppDomain.CurrentDomain.BaseDirectory;
        private static readonly Dictionary<string, JsonElement> _cfg = LoadConfig();

        public static readonly string AssetsDir = ResolveAssetsDir();
        public static readonly string ReactvisionExe = ResolveReactvisionExe();
        public static readonly string TuioHost = ReadString("tuio_host", "0.0.0.0");
        public static readonly int TuioPort = ReadInt("tuio_port", 3333);
        /// <summary>Minimum absolute angle change (radians) on /tuio/2Dobj before a rotation event fires.</summary>
        public static readonly float TuioRotationThresholdRad = ReadFloat("rotation_threshold", 0.45f);
        public static readonly int MenuTuioMarker = ReadInt("menu_tuio_marker", 10);
        public static readonly int AdminTuioMarker = ReadInt("admin_tuio_marker", 9);
        /// <summary>Stored in config for reference; admin gate matches by <see cref="AdminBluetoothName"/> only.</summary>
        public static readonly string AdminBluetoothMac = ReadString("admin_bluetooth_mac", "");
        public static readonly string AdminBluetoothName = ReadString("admin_bluetooth_name", "");
        public static readonly bool AdminBluetoothForce = ReadBool("admin_bluetooth_force", false);
        /// <summary>If true, admin unlocks when any paired Bluetooth peripheral is present (OK), instead of matching name.</summary>
        public static readonly bool AdminBluetoothAutoConnected = ReadBool("admin_bluetooth_auto_connected", false);
        public static readonly int AdminBtPollSeconds = ReadInt("admin_bluetooth_poll_seconds", 3);
        public static readonly string RepoRoot = ResolveRepoRoot();
        public static readonly string AdminUsersJsonPath = Path.Combine(RepoRoot, "admin_users.json");
        public static readonly float MenuVolumeStep = ReadFloat("menu_volume_step", 0.045f);
        public static readonly double MenuVolRepeatSec = ReadFloat("menu_volume_repeat_seconds", 0.25f);
        public static readonly double MenuActionCooldown = ReadFloat("menu_action_cooldown_seconds", 2f);
        public static readonly float MenuMotionThresh = ReadFloat("menu_motion_threshold", 0.04f);
        public static readonly float MenuSmoothAlpha = ReadFloat("menu_smooth_alpha", 0.4f);
        public static readonly float MenuCursorGain = ReadFloat("menu_cursor_gain", 520f);

        private static string ResolveRepoRoot()
        {
            string cfg = FindFileUpTree(BaseDir, "config.json");
            if (!string.IsNullOrEmpty(cfg))
                return Path.GetDirectoryName(cfg) ?? BaseDir;
            return BaseDir;
        }

        private static Dictionary<string, JsonElement> LoadConfig()
        {
            var result = new Dictionary<string, JsonElement>(StringComparer.OrdinalIgnoreCase);
            string logPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "bt_gate.log");
            try
            {
                string p = FindFileUpTree(BaseDir, "config.json");
                File.AppendAllText(logPath,
                    $"[{DateTime.Now:HH:mm:ss}] LoadConfig: BaseDir=\"{BaseDir}\" resolved=\"{p}\"{Environment.NewLine}");
                if (string.IsNullOrEmpty(p)) return result;
                using var doc = JsonDocument.Parse(File.ReadAllText(p, Encoding.UTF8));
                foreach (var prop in doc.RootElement.EnumerateObject())
                {
                    result[prop.Name] = prop.Value.Clone();
                }
                if (result.TryGetValue("admin_bluetooth_name", out var nameEl))
                {
                    File.AppendAllText(logPath,
                        $"[{DateTime.Now:HH:mm:ss}] LoadConfig: admin_bluetooth_name kind={nameEl.ValueKind} raw=\"{nameEl.GetRawText()}\"{Environment.NewLine}");
                }
                else
                {
                    File.AppendAllText(logPath,
                        $"[{DateTime.Now:HH:mm:ss}] LoadConfig: admin_bluetooth_name key NOT present. Keys: {string.Join(",", result.Keys)}{Environment.NewLine}");
                }
            }
            catch (Exception ex)
            {
                try
                {
                    File.AppendAllText(logPath,
                        $"[{DateTime.Now:HH:mm:ss}] LoadConfig EXCEPTION: {ex.GetType().Name}: {ex.Message}{Environment.NewLine}");
                }
                catch { }
            }
            return result;
        }

        private static string ResolveReactvisionExe()
        {
            string cfg = ReadString("reactvision_exe", "");
            if (!string.IsNullOrWhiteSpace(cfg))
            {
                string candidate = Path.IsPathRooted(cfg)
                    ? cfg
                    : Path.GetFullPath(Path.Combine(Path.GetDirectoryName(FindFileUpTree(BaseDir, "config.json") ?? BaseDir) ?? BaseDir, cfg));
                if (File.Exists(candidate)) return candidate;
            }
            string repoRoot = ResolveRepoRoot();
            string bundled = Path.Combine(repoRoot, "reacTIVision-1.5.1-win64", "reacTIVision.exe");
            if (File.Exists(bundled)) return bundled;
            return "";
        }

        private static string ResolveAssetsDir()
        {
            try
            {
                string[] candidates =
                {
                    Path.Combine(BaseDir, "assets"),
                    Path.GetFullPath(Path.Combine(BaseDir, "..", "..", "assets")),
                    Path.GetFullPath(Path.Combine(BaseDir, "..", "..", "..", "assets"))
                };

                foreach (string candidate in candidates)
                {
                    if (Directory.Exists(candidate))
                        return candidate;
                }
            }
            catch { }

            return Path.Combine(BaseDir, "assets");
        }

        public static string GetAssetPath(string fileName)
        {
            return Path.Combine(AssetsDir, fileName);
        }

        private static string FindFileUpTree(string startDir, string fileName)
        {
            try
            {
                var dir = new DirectoryInfo(startDir);
                for (int i = 0; i < 8 && dir != null; i++, dir = dir.Parent)
                {
                    string candidate = Path.Combine(dir.FullName, fileName);
                    if (File.Exists(candidate)) return candidate;
                }
            }
            catch { }
            return "";
        }

        private static string ReadString(string key, string fallback)
        {
            if (_cfg != null &&
                _cfg.TryGetValue(key, out var el) &&
                el.ValueKind == JsonValueKind.String)
            {
                return el.GetString() ?? fallback;
            }
            return fallback;
        }

        private static int ReadInt(string key, int fallback)
        {
            if (_cfg != null && _cfg.TryGetValue(key, out var el) && el.TryGetInt32(out int i)) return i;
            return fallback;
        }

        private static bool ReadBool(string key, bool fallback)
        {
            if (_cfg != null && _cfg.TryGetValue(key, out var el))
            {
                if (el.ValueKind == JsonValueKind.True) return true;
                if (el.ValueKind == JsonValueKind.False) return false;
            }
            return fallback;
        }

        private static float ReadFloat(string key, float fallback)
        {
            if (_cfg != null && _cfg.TryGetValue(key, out var el))
            {
                if (el.TryGetDouble(out double d)) return (float)d;
                if (el.ValueKind == JsonValueKind.String &&
                    float.TryParse(el.GetString(), System.Globalization.NumberStyles.Float,
                        System.Globalization.CultureInfo.InvariantCulture, out float fs))
                    return fs;
            }
            return fallback;
        }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    //  CHARACTER MAP
    // ═══════════════════════════════════════════════════════════════════════════

    public static class CharacterMap
    {
        public static Dictionary<int, UserProfile> GetAllUsers()
        {
            return new Dictionary<int, UserProfile>
            {
                [0] = new UserProfile
                {
                    Name = "Shark",
                    Bg = ColorTranslator.FromHtml("#0a0e1a"),
                    HeaderBg = ColorTranslator.FromHtml("#0d1b2a"),
                    Accent = ColorTranslator.FromHtml("#00b4d8"),
                    Fg = Color.White,
                    Glow = ColorTranslator.FromHtml("#90e0ef"),
                    AvatarPath = AppConfig.GetAssetPath("blue user.jpg"),
                    GifPath = AppConfig.GetAssetPath("blue animation.gif"),
                },
                [1] = new UserProfile
                {
                    Name = "Rogue",
                    Bg = ColorTranslator.FromHtml("#0e0a1a"),
                    HeaderBg = ColorTranslator.FromHtml("#1a0d2e"),
                    Accent = ColorTranslator.FromHtml("#9d4edd"),
                    Fg = Color.White,
                    Glow = ColorTranslator.FromHtml("#c77dff"),
                    AvatarPath = AppConfig.GetAssetPath("purple user.jpg"),
                    GifPath = AppConfig.GetAssetPath("purple animation.gif"),
                },
                [2] = new UserProfile
                {
                    Name = "Ditto",
                    Bg = ColorTranslator.FromHtml("#0a1a0e"),
                    HeaderBg = ColorTranslator.FromHtml("#0d2a13"),
                    Accent = ColorTranslator.FromHtml("#57cc99"),
                    Fg = Color.White,
                    Glow = ColorTranslator.FromHtml("#80ed99"),
                    AvatarPath = AppConfig.GetAssetPath("green user.jpg"),
                    GifPath = AppConfig.GetAssetPath("green animation.gif"),
                },
                [3] = new UserProfile
                {
                    Name = "Arthur",
                    Bg = ColorTranslator.FromHtml("#1a0a0a"),
                    HeaderBg = ColorTranslator.FromHtml("#2a0d0d"),
                    Accent = ColorTranslator.FromHtml("#ff6b6b"),
                    Fg = Color.White,
                    Glow = ColorTranslator.FromHtml("#ff9e9e"),
                    AvatarPath = AppConfig.GetAssetPath("orange user.jpg"),
                    GifPath = AppConfig.GetAssetPath("orange animation.gif"),
                },
            };
        }

        /// <summary>Theme preset rotated by marker id (Python user_store.build_user_dict).</summary>
        public static UserProfile BuildUserProfile(int markerId, string name)
        {
            var all = GetAllUsers();
            int k = ((markerId % 4) + 4) % 4;
            var t = all[k];
            return new UserProfile
            {
                Name = name,
                Bg = t.Bg,
                HeaderBg = t.HeaderBg,
                Accent = t.Accent,
                Fg = t.Fg,
                Glow = t.Glow,
                AvatarPath = t.AvatarPath,
                GifPath = t.GifPath,
            };
        }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    //  GIF PLAYER  — Timer-based, no ImageAnimator
    // ═══════════════════════════════════════════════════════════════════════════

    public class GifPlayer : IDisposable
    {
        private readonly Bitmap[] _frames;
        private readonly int[] _delays;
        private int _frameIndex = 0;
        private readonly System.Windows.Forms.Timer _timer;
        private readonly Action<Bitmap> _onFrame;

        public GifPlayer(string path, Action<Bitmap> onFrameChanged)
        {
            _onFrame = onFrameChanged;

            if (!File.Exists(path))
            {
                MessageBox.Show("GIF NOT FOUND:\n" + path);
                _frames = Array.Empty<Bitmap>();
                _delays = Array.Empty<int>();
                return;
            }

            try
            {
                using var src = Image.FromFile(path);
                var dim = new FrameDimension(src.FrameDimensionsList[0]);
                int count = src.GetFrameCount(dim);

                _frames = new Bitmap[count];
                _delays = new int[count];

                byte[] rawDelays = src.GetPropertyItem(0x5100).Value;

                for (int i = 0; i < count; i++)
                {
                    src.SelectActiveFrame(dim, i);
                    _frames[i] = new Bitmap(src);
                    int cs = BitConverter.ToInt32(rawDelays, i * 4);
                    _delays[i] = Math.Max(cs * 10, 20);
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show("GIF LOAD ERROR:\n" + ex.Message);
                _frames = Array.Empty<Bitmap>();
                _delays = Array.Empty<int>();
                return;
            }

            if (_frames.Length == 0) return;

            _onFrame?.Invoke(_frames[0]);

            _timer = new System.Windows.Forms.Timer { Interval = _delays[0] };
            _timer.Tick += (s, e) =>
            {
                _frameIndex = (_frameIndex + 1) % _frames.Length;
                _timer.Interval = _delays[_frameIndex];
                _onFrame?.Invoke(_frames[_frameIndex]);
            };
            _timer.Start();
        }

        public void Dispose()
        {
            _timer?.Stop();
            _timer?.Dispose();
            foreach (var f in _frames) f?.Dispose();
        }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    //  AVATAR HELPER
    // ═══════════════════════════════════════════════════════════════════════════

    public static class AvatarHelper
    {
        public static Bitmap Make(string path, int size, Color accent)
        {
            var bmp = new Bitmap(size, size, PixelFormat.Format32bppArgb);
            using var g = Graphics.FromImage(bmp);
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            g.PixelOffsetMode = PixelOffsetMode.HighQuality;
            g.Clear(Color.Transparent);

            using var clip = new GraphicsPath();
            clip.AddEllipse(0, 0, size, size);
            g.SetClip(clip);

            using var bgBrush = new SolidBrush(Color.FromArgb(120, accent));
            g.FillEllipse(bgBrush, 0, 0, size, size);

            bool loaded = false;
            if (File.Exists(path))
            {
                try
                {
                    byte[] bytes = File.ReadAllBytes(path);
                    using var ms = new MemoryStream(bytes);
                    using var src = new Bitmap(Image.FromStream(ms));
                    g.DrawImage(src, 0, 0, size, size);
                    loaded = true;
                }
                catch { }
            }

            if (!loaded)
            {
                string fname = Path.GetFileNameWithoutExtension(path ?? "");
                string initial = fname.Length > 0 ? fname[0].ToString().ToUpper() : "?";
                using var initFont = new Font("Impact", size * 0.42f, FontStyle.Bold);
                using var initBrush = new SolidBrush(Color.FromArgb(230, accent));
                SizeF isz = g.MeasureString(initial, initFont);
                g.DrawString(initial, initFont, initBrush,
                             (size - isz.Width) / 2f, (size - isz.Height) / 2f);
            }

            g.ResetClip();
            using var ring = new Pen(accent, 3);
            g.DrawEllipse(ring, 1.5f, 1.5f, size - 3f, size - 3f);

            return bmp;
        }
    }

    public sealed class BluetoothAdminGate : IDisposable
    {
        /// <summary>Kept for config compatibility; admin unlock does not use MAC matching.</summary>
        private readonly string _macIgnored;
        private readonly string _name;
        private readonly bool _force;
        private readonly bool _autoConnected;
        private readonly System.Windows.Forms.Timer _timer;
        public static readonly string LogPath =
            Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "bt_gate.log");

        public bool IsConnected { get; private set; }

        /// <summary>Windows friendly name of the paired peripheral that satisfied the gate, if any.</summary>
        public string MatchedBluetoothName { get; private set; }

        public BluetoothAdminGate(string mac, string name, bool force, bool autoConnected, int pollSeconds = 3)
        {
            _macIgnored = NormalizeMac(mac);
            _name = NormalizeBluetoothNameKey(name);
            _force = force;
            _autoConnected = autoConnected;
            _timer = new System.Windows.Forms.Timer
            {
                Interval = Math.Max(1, pollSeconds) * 1000
            };
            _timer.Tick += (s, e) => Refresh();
            WriteLog($"ctor: raw_name=\"{name}\" raw_name_len={(name ?? "").Length} norm_name=\"{_name}\" norm_name_len={_name.Length} force={_force} autoConnected={_autoConnected} mac_cfg=\"{_macIgnored}\"");
        }

        public void Start()
        {
            Refresh();
            _timer.Start();
        }

        public void Stop() => _timer.Stop();

        public void Refresh()
        {
            MatchedBluetoothName = null;
            if (_force)
            {
                IsConnected = true;
                MatchedBluetoothName = "(force unlock)";
                WriteLog($"force_connected=true → IsConnected=TRUE");
                return;
            }

            var devices = QueryEligibleBluetoothPeripherals();
            string pnpList = devices.Count == 0
                ? "(none)"
                : string.Join(" | ", devices.ConvertAll(d => $"\"{d.FriendlyName}\""));
            WriteLog($"pnp devices: {pnpList}");

            if (_autoConnected)
            {
                IsConnected = devices.Count > 0;
                if (IsConnected) MatchedBluetoothName = devices[0].FriendlyName;
                WriteLog($"auto_connected=true → IsConnected={IsConnected} match=\"{MatchedBluetoothName}\"");
                return;
            }

            if (string.IsNullOrWhiteSpace(_name))
            {
                IsConnected = false;
                WriteLog("admin_bluetooth_name blank and auto_connected=false → IsConnected=FALSE");
                return;
            }

            foreach (var d in devices)
            {
                string norm = NormalizeBluetoothNameKey(d.FriendlyName);
                bool hit = norm.Contains(_name, StringComparison.Ordinal);
                WriteLog($"pnp check \"{d.FriendlyName}\" norm=\"{norm}\" want=\"{_name}\" hit={hit}");
                if (hit)
                {
                    IsConnected = true;
                    MatchedBluetoothName = d.FriendlyName;
                    WriteLog($"pnp MATCH → IsConnected=TRUE");
                    return;
                }
            }

            // NOTE: we intentionally do NOT fall back to the paired-devices registry here.
            // The registry only records pairing, not live connection, so a paired-but-
            // disconnected phone would perma-unlock the admin screen.

            IsConnected = false;
            WriteLog($"no match for want=\"{_name}\" (paired-only devices don't count) → IsConnected=FALSE");
        }

        private static void WriteLog(string line)
        {
            try
            {
                File.AppendAllText(LogPath,
                    $"[{DateTime.Now:HH:mm:ss}] {line}{Environment.NewLine}");
            }
            catch { }
        }

        /// <summary>Lowercase + normalize apostrophes (ASCII vs U+2019) for matching.</summary>
        private static string NormalizeBluetoothNameKey(string value)
        {
            if (string.IsNullOrWhiteSpace(value)) return "";
            return value.Trim().ToLowerInvariant()
                .Replace('\u2019', '\'').Replace('\u2018', '\'');
        }

        private readonly struct BtPnpRow
        {
            public BtPnpRow(string friendlyName) => FriendlyName = friendlyName;
            public string FriendlyName { get; }
        }

        /// <summary>
        /// Returns Bluetooth devices that are ACTIVELY CONNECTED (not merely paired).
        /// Windows keeps the parent <c>BTHENUM\DEV_&lt;MAC&gt;</c>/ <c>BTHLE\DEV_&lt;MAC&gt;</c>
        /// entry <c>Present=True</c> for any paired device (because of
        /// <c>AlwaysShowDeviceAsConnected</c>), so we cannot rely on it.
        /// Instead we require at least one service-child (A2DP, HFP, AVRCP, …) whose
        /// <c>InstanceId</c> contains the parent's MAC and which is itself <c>Present=True</c>.
        /// Those children disappear the moment the phone disconnects.
        /// </summary>
        private static List<BtPnpRow> QueryEligibleBluetoothPeripherals()
        {
            const string script = @"
$parents = Get-PnpDevice -Class Bluetooth -PresentOnly -ErrorAction SilentlyContinue | Where-Object {
    $_.Status -notin @('Error','Degraded') -and
    (
        $_.InstanceId -match '^BTHENUM\\DEV_([0-9A-F]{12})' -or
        $_.InstanceId -match '^BTHLE\\DEV_([0-9A-F]{12,})'
    ) -and
    $_.FriendlyName -notlike '*Enumerator*' -and
    $_.FriendlyName -notlike '*Wireless Bluetooth*'
}
$allPresent = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue
$out = @()
foreach ($p in $parents) {
    $mac = $null
    if ($p.InstanceId -match '^BTHENUM\\DEV_([0-9A-F]{12})')  { $mac = $Matches[1] }
    elseif ($p.InstanceId -match '^BTHLE\\DEV_([0-9A-F]{12,})') { $mac = $Matches[1] }
    if (-not $mac) { continue }
    $children = $allPresent | Where-Object {
        $_.InstanceId -ne $p.InstanceId -and $_.InstanceId -match $mac
    }
    if ($children.Count -gt 0) {
        $out += $p.FriendlyName
    }
}
@($out) | ConvertTo-Json -Compress
";
            string json = (RunPowerShellEncoded(script) ?? "").Trim();
            return ParseFriendlyNameJsonArray(json);
        }

        /// <summary>True if a device paired to this PC has a matching friendly name (Bluetooth registration DB).</summary>
        private static bool TryFindPairedDeviceNameInRegistry(string nameKeyNorm, out string friendlyDisplay)
        {
            friendlyDisplay = null;
            if (string.IsNullOrEmpty(nameKeyNorm)) return false;
            try
            {
                using RegistryKey key = Registry.LocalMachine.OpenSubKey(
                    @"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices");
                if (key == null) return false;
                foreach (string subName in key.GetSubKeyNames())
                {
                    using RegistryKey subPtr = key.OpenSubKey(subName);
                    if (subPtr == null) continue;
                    object raw = subPtr.GetValue("Name");
                    string friendly = DecodeBluetoothRegistryName(raw);
                    if (string.IsNullOrWhiteSpace(friendly)) continue;
                    if (NormalizeBluetoothNameKey(friendly).Contains(nameKeyNorm, StringComparison.Ordinal))
                    {
                        friendlyDisplay = friendly.Trim();
                        return true;
                    }
                }
            }
            catch { }
            return false;
        }

        private static string DecodeBluetoothRegistryName(object raw)
        {
            if (raw == null) return "";
            if (raw is byte[] bytes && bytes.Length > 0)
            {
                if (bytes.Length >= 2 && bytes[1] == 0)
                    return Encoding.Unicode.GetString(bytes).TrimEnd('\0').Trim();
                return Encoding.UTF8.GetString(bytes).TrimEnd('\0').Trim();
            }
            return raw.ToString()?.Trim() ?? "";
        }

        private static List<BtPnpRow> ParseFriendlyNameJsonArray(string json)
        {
            var list = new List<BtPnpRow>();
            if (string.IsNullOrWhiteSpace(json)) return list;
            try
            {
                using var doc = JsonDocument.Parse(json);
                var root = doc.RootElement;
                if (root.ValueKind == JsonValueKind.Array)
                {
                    foreach (var el in root.EnumerateArray())
                    {
                        if (el.ValueKind == JsonValueKind.String)
                        {
                            string s = el.GetString();
                            if (!string.IsNullOrWhiteSpace(s)) list.Add(new BtPnpRow(s));
                        }
                    }
                }
                else if (root.ValueKind == JsonValueKind.String)
                {
                    string s = root.GetString();
                    if (!string.IsNullOrWhiteSpace(s)) list.Add(new BtPnpRow(s));
                }
            }
            catch { }
            return list;
        }

        private static string RunPowerShellEncoded(string script)
        {
            try
            {
                string b64 = Convert.ToBase64String(Encoding.Unicode.GetBytes(script));
                var psi = new ProcessStartInfo("powershell.exe",
                    $"-NoProfile -ExecutionPolicy Bypass -EncodedCommand {b64}")
                {
                    CreateNoWindow = true,
                    UseShellExecute = false,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                };
                using var p = Process.Start(psi);
                if (p == null) return "";
                string output = p.StandardOutput.ReadToEnd();
                p.WaitForExit(8000);
                return output;
            }
            catch
            {
                return "";
            }
        }

        private static string NormalizeMac(string value)
        {
            return (value ?? "").Trim().ToLowerInvariant().Replace("-", ":");
        }

        public void Dispose()
        {
            Stop();
            _timer.Dispose();
        }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    //  PAINT CANVAS
    // ═══════════════════════════════════════════════════════════════════════════

    public class PaintCanvas : Panel
    {
        public PaintCanvas()
        {
            SetStyle(
                ControlStyles.UserPaint |
                ControlStyles.AllPaintingInWmPaint |
                ControlStyles.OptimizedDoubleBuffer |
                ControlStyles.SupportsTransparentBackColor,
                true);
            BackColor = Color.Transparent;
        }
        protected override void OnPaintBackground(PaintEventArgs e) { /* transparent */ }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    //  CIRCULAR MENU OVERLAY
    //  — Transparent topmost Form driven by TUIO marker rotation.
    //    The form's background is punched out via TransparencyKey so only
    //    the wedge shapes are visible over whatever is underneath.
    // ═══════════════════════════════════════════════════════════════════════════

    public class CircularMenuOverlay : Form
    {
        // ── transparency colour — must never appear in drawn wedges ────────────
        private static readonly Color TransKey = Color.FromArgb(1, 2, 3);

        // ── IsActive property so GUIForm can check visibility ─────────────────
        public bool IsActive => Visible;

        // ── TUIO marker angle comes from GUIForm's single TuioAdapter (one UDP port).
        private float _markerAngle = -1f;
        private string _hoveredWedge = "center";

        private DateTime _lastGlobalAction = DateTime.MinValue;
        private DateTime _lastVolTime = DateTime.MinValue;
        private string _lastTriggeredSector = "";

        private const double ActionCooldownS = 2.2;
        private const double VolRepeatS = 0.25;

        /// <summary>Called from GUIForm when /tuio/2Dobj set includes angle for the menu fid.</summary>
        public void FeedMenuMarkerAngle(int markerId, float angleRadians)
        {
            if (markerId != AppConfig.MenuTuioMarker) return;
            _markerAngle = angleRadians;
        }

        /// <summary>Clear wedge pointer when the menu marker is removed.</summary>
        public void ResetMenuMarkerTracking()
        {
            _markerAngle = -1f;
        }

        // ── wedge callbacks ───────────────────────────────────────────────────
        private readonly Action _onLeft;
        private readonly Action _onRight;
        private readonly Action _onRightUp;
        private readonly Action _onRightDown;
        private readonly Action _onVolUp;
        private readonly Action _onVolDown;

        // ── wedge spec ────────────────────────────────────────────────────────
        private class WedgeSpec
        {
            public string Name;
            public float StartAngle, SweepAngle;
            public Color DimColor, BrightColor;
            public string Text;
            public Font TextFont;
            public PointF TextOffset;
        }
        private List<WedgeSpec> _wedges;

        // ── ctor ──────────────────────────────────────────────────────────────
        public CircularMenuOverlay(
            Control parent,
            Action onLeft, Action onRight,
            Action onRightUp, Action onRightDown,
            Action onVolUp, Action onVolDown)
        {
            _onLeft = onLeft;
            _onRight = onRight;
            _onRightUp = onRightUp;
            _onRightDown = onRightDown;
            _onVolUp = onVolUp;
            _onVolDown = onVolDown;

            // ── window properties ─────────────────────────────────────────────
            FormBorderStyle = FormBorderStyle.None;
            WindowState = FormWindowState.Maximized;
            TopMost = true;
            DoubleBuffered = true;
            ShowInTaskbar = false;

            // ── transparency ──────────────────────────────────────────────────
            BackColor = TransKey;
            TransparencyKey = TransKey;
            SetStyle(ControlStyles.SupportsTransparentBackColor, true);

            // ── start hidden ──────────────────────────────────────────────────
            Visible = false;

            InitWedges();

            // No per-overlay UDP — shares FruitNinjaGame.TuioAdapter on port 3333.

            // ── render / logic timer (~60 fps) ────────────────────────────────
            var timer = new System.Windows.Forms.Timer { Interval = 16 };
            timer.Tick += Timer_Tick;
            timer.Start();
        }

        // ── make transparent pixels click-through ─────────────────────────────
        protected override CreateParams CreateParams
        {
            get
            {
                var cp = base.CreateParams;
                cp.ExStyle |= 0x00080000; // WS_EX_LAYERED
                cp.ExStyle |= 0x00000020; // WS_EX_TRANSPARENT
                return cp;
            }
        }

        // ── public show / hide ────────────────────────────────────────────────
        public void ShowMenu()
        {
            Visible = true;
            BringToFront();
            Invalidate();
        }

        public void HideMenu()
        {
            Visible = false;
        }

        // ── wedge definitions ─────────────────────────────────────────────────
        private void InitWedges()
        {
            _wedges = new List<WedgeSpec>();
            Font fontLarge = new Font("Bahnschrift", 20, FontStyle.Bold);
            Font fontSmall = new Font("Bahnschrift", 16, FontStyle.Regular);

            _wedges.Add(new WedgeSpec
            {
                Name = "right",
                StartAngle = 0f,
                SweepAngle = 60f,
                DimColor = ColorTranslator.FromHtml("#1a2a4a"),
                BrightColor = ColorTranslator.FromHtml("#5b8cff"),
                Text = "MIN OTHERS\n+ GUI",
                TextFont = fontLarge,
                TextOffset = new PointF(214, 124)
            });

            _wedges.Add(new WedgeSpec
            {
                Name = "down",
                StartAngle = 60f,
                SweepAngle = 60f,
                DimColor = ColorTranslator.FromHtml("#3d2a1a"),
                BrightColor = ColorTranslator.FromHtml("#ffb020"),
                Text = "VOL -",
                TextFont = fontLarge,
                TextOffset = new PointF(0, 248)
            });

            _wedges.Add(new WedgeSpec
            {
                Name = "right_down",
                StartAngle = 120f,
                SweepAngle = 60f,
                DimColor = ColorTranslator.FromHtml("#2a3555"),
                BrightColor = ColorTranslator.FromHtml("#7eb8ff"),
                Text = "GUI\n(full)\nif game FS",
                TextFont = fontSmall,
                TextOffset = new PointF(-214, 124)
            });

            _wedges.Add(new WedgeSpec
            {
                Name = "left",
                StartAngle = 180f,
                SweepAngle = 60f,
                DimColor = ColorTranslator.FromHtml("#3d1a2a"),
                BrightColor = ColorTranslator.FromHtml("#ff5b8c"),
                Text = "EXIT GAME\n+ GUI",
                TextFont = fontLarge,
                TextOffset = new PointF(-214, -124)
            });

            _wedges.Add(new WedgeSpec
            {
                Name = "up",
                StartAngle = 240f,
                SweepAngle = 60f,
                DimColor = ColorTranslator.FromHtml("#1a3d2e"),
                BrightColor = ColorTranslator.FromHtml("#2ee59d"),
                Text = "VOL +",
                TextFont = fontLarge,
                TextOffset = new PointF(0, -248)
            });

            _wedges.Add(new WedgeSpec
            {
                Name = "right_up",
                StartAngle = 300f,
                SweepAngle = 60f,
                DimColor = ColorTranslator.FromHtml("#2a3d5a"),
                BrightColor = ColorTranslator.FromHtml("#6ec0ff"),
                Text = "GAME ->\nGUI\n(fullscr)",
                TextFont = fontSmall,
                TextOffset = new PointF(214, -124)
            });
        }

        // ── marker angle supplied by TuioAdapter via FeedMenuMarkerAngle ────

        // ── timer ─────────────────────────────────────────────────────────────
        private void Timer_Tick(object sender, EventArgs e)
        {
            UpdateLogic();
            if (Visible) Invalidate();
        }

        // ── logic ─────────────────────────────────────────────────────────────
        private void UpdateLogic()
        {
            if (_markerAngle < 0) return;

            float degrees = _markerAngle * 180f / (float)Math.PI;
            float graphicsAngle = degrees - 90f;
            if (graphicsAngle < 0) graphicsAngle += 360f;

            _hoveredWedge = "center";
            foreach (var w in _wedges)
            {
                float end = w.StartAngle + w.SweepAngle;
                bool inside = end > 360f
                    ? (graphicsAngle >= w.StartAngle || graphicsAngle <= end - 360f)
                    : (graphicsAngle >= w.StartAngle && graphicsAngle <= end);
                if (inside) { _hoveredWedge = w.Name; break; }
            }

            DateTime now = DateTime.Now;

            if (_hoveredWedge == "up" || _hoveredWedge == "down")
            {
                if ((now - _lastVolTime).TotalSeconds >= VolRepeatS)
                {
                    _lastVolTime = now;
                    if (_hoveredWedge == "up") { _onVolUp?.Invoke(); Console.WriteLine("ACTION: Volume UP"); }
                    else { _onVolDown?.Invoke(); Console.WriteLine("ACTION: Volume DOWN"); }
                }
            }
            else if (_hoveredWedge != "center" && _hoveredWedge != _lastTriggeredSector)
            {
                if ((now - _lastGlobalAction).TotalSeconds >= ActionCooldownS)
                {
                    _lastGlobalAction = now;
                    Console.WriteLine($"ACTION: Triggered {_hoveredWedge}");
                    switch (_hoveredWedge)
                    {
                        case "left": _onLeft?.Invoke(); break;
                        case "right": _onRight?.Invoke(); break;
                        case "right_up": _onRightUp?.Invoke(); break;
                        case "right_down": _onRightDown?.Invoke(); break;
                    }
                }
            }

            _lastTriggeredSector = _hoveredWedge;
        }

        // ── paint ─────────────────────────────────────────────────────────────
        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;

            int cx = Width / 2;
            int cy = Height / 2;
            int R = (int)(Math.Min(Width, Height) * 0.28f);

            // outer ring (drawn only — background punched through)
            using (var outlinePen = new Pen(Color.FromArgb(80, 42, 42, 68), 2))
                g.DrawEllipse(outlinePen, cx - R - 40, cy - R - 40, (R + 40) * 2, (R + 40) * 2);

            var rect = new Rectangle(cx - R, cy - R, R * 2, R * 2);

            foreach (var w in _wedges)
            {
                Color fillWithAlpha = _hoveredWedge == w.Name
                    ? Color.FromArgb(230, w.BrightColor)
                    : Color.FromArgb(200, w.DimColor);

                using (var brush = new SolidBrush(fillWithAlpha))
                    g.FillPie(brush, rect, w.StartAngle, w.SweepAngle);

                using (var pen = new Pen(Color.FromArgb(100, 68, 68, 102), 2))
                    g.DrawPie(pen, rect, w.StartAngle, w.SweepAngle);

                var sf = new StringFormat
                {
                    Alignment = StringAlignment.Center,
                    LineAlignment = StringAlignment.Center
                };
                using (var textBrush = new SolidBrush(Color.FromArgb(220, 204, 204, 204)))
                    g.DrawString(w.Text, w.TextFont, textBrush,
                                 cx + w.TextOffset.X, cy + w.TextOffset.Y, sf);
            }

            // TUIO cursor
            if (_markerAngle >= 0)
            {
                float deg = _markerAngle * 180f / (float)Math.PI;
                float gAng = deg - 90f;
                float rad = gAng * (float)Math.PI / 180f;
                float px = (float)Math.Cos(rad) * (R - 20);
                float py = (float)Math.Sin(rad) * (R - 20);

                using (var linePen = new Pen(Color.FromArgb(200, 255, 255, 255), 3))
                    g.DrawLine(linePen, cx, cy, cx + px, cy + py);

                using (var dotBrush = new SolidBrush(Color.White))
                using (var dotPen = new Pen(ColorTranslator.FromHtml("#00fff7"), 3))
                {
                    g.FillEllipse(dotBrush, cx + px - 14, cy + py - 14, 28, 28);
                    g.DrawEllipse(dotPen, cx + px - 14, cy + py - 14, 28, 28);
                }
            }

            // instructions
            using (var instFont = new Font("Consolas", 12))
            using (var instBrush = new SolidBrush(Color.FromArgb(140, 102, 102, 136)))
            {
                var sf = new StringFormat { Alignment = StringAlignment.Center };
                g.DrawString(
                    $"Rotate TUIO marker {AppConfig.MenuTuioMarker} to select a wedge.  Actions have a {ActionCooldownS}s cooldown.",
                    instFont, instBrush, cx, Height - 60, sf);
                g.DrawString("Press ESC to close", instFont, instBrush, 100, 50);
            }
        }

        // ── keyboard ──────────────────────────────────────────────────────────
        protected override void OnKeyDown(KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Escape) HideMenu();
            base.OnKeyDown(e);
        }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    //  FORM1  (GUIForm)
    // ═══════════════════════════════════════════════════════════════════════════

    public partial class GUIForm : Form
    {
        private readonly Dictionary<int, UserProfile> _users;
        private int? _currentUser = null;
        private bool _rotationTriggered = false;
        private bool _useTuioControl = false;
        private Control _screen = null;
        private GifPlayer _gifPlayer = null;
        private Bitmap _currentGifFrame = null;
        private Panel _tuioLight = null;
        private Process _reactivisionProcess = null;
        private bool _gameRunning = false;
        private Form1 _activeGameForm = null;

        private readonly List<Bitmap> _screenBitmaps = new List<Bitmap>();

        private System.Windows.Forms.Timer _blinkTimer = null;
        private Label _blinkLabel = null;
        private bool _blinkState = true;

        // Single declaration — CircularMenuOverlay is now the transparent Form
        private CircularMenuOverlay _menuOverlay = null;
        private TuioAdapter _tuioAdapter = null;
        private BluetoothAdminGate _adminGate = null;
        private bool _adminMode = false;
        private FlowLayoutPanel _adminListFlow = null;
        private int _adminSelected = 0;
        private float? _adminNeutralY = null;
        private float _adminSmoothedY = 0f;
        private bool _adminTriggered = false;

        // ── ctor ───────────────────────────────────────────────────────────────
        public GUIForm()
        {
            InitializeComponent();

            _users = UserStore.LoadUsers();

            Text = "Gesture-Powered Virtual Game Control";
            FormBorderStyle = FormBorderStyle.None;
            WindowState = FormWindowState.Maximized;
            BackColor = Color.Black;
            DoubleBuffered = true;
            KeyPreview = true;

            KeyDown += OnKeyDown;
            FormClosing += (s, e) => OnAppExit();
            Load += OnFormLoad;
            Resize += (s, e) =>
            {
                // The overlay is now a separate topmost Form — no bounds to sync
            };
        }

        // ── load ───────────────────────────────────────────────────────────────
        private void OnFormLoad(object sender, EventArgs e)
        {
            // CircularMenuOverlay is a transparent topmost Form.
            // We pass 'this' as parent only so the overlay stays alive with GUIForm;
            // it manages its own window — no Bounds sync needed.
            _menuOverlay = new CircularMenuOverlay(
                this,
                onLeft: MenuActionLeft,
                onRight: MenuActionRight,
                onRightUp: MenuActionRightUp,
                onRightDown: MenuActionRightDown,
                onVolUp: () => { },
                onVolDown: () => { }
            );

            _tuioAdapter = new TuioAdapter(
                AppConfig.TuioHost,
                AppConfig.TuioPort,
                onMarkerDetected: fid => OnMarkerDetected(fid),
                onMarkerRemoved: fid => OnMarkerRemoved(fid),
                onMarkerRotated: (dir, fid) => OnMarkerRotated(dir, fid),
                rotationThresholdRad: AppConfig.TuioRotationThresholdRad,
                onMarkerMoved: (fid, x, y, a) => OnTuioMarkerMoved(fid, x, y, a)
            );
            _tuioAdapter.Start();

            _adminGate = new BluetoothAdminGate(
                AppConfig.AdminBluetoothMac,
                AppConfig.AdminBluetoothName,
                AppConfig.AdminBluetoothForce,
                AppConfig.AdminBluetoothAutoConnected,
                AppConfig.AdminBtPollSeconds
            );
            _adminGate.Start();

            LaunchReactivision();
            ShowMainMenu();
        }

        // ── exit ───────────────────────────────────────────────────────────────
        private void OnAppExit()
        {
            _adminGate?.Stop();
            _adminGate?.Dispose();
            _adminGate = null;

            _tuioAdapter?.Stop();
            _tuioAdapter?.Dispose();
            _tuioAdapter = null;

            StopReactivision();
            _blinkTimer?.Stop();
            _gifPlayer?.Dispose();
            FreeScreenBitmaps();
            _menuOverlay?.Close();
        }

        // ── bitmap lifetime ────────────────────────────────────────────────────
        private Bitmap Track(Bitmap bmp) { _screenBitmaps.Add(bmp); return bmp; }
        private void FreeScreenBitmaps()
        {
            foreach (var b in _screenBitmaps) b?.Dispose();
            _screenBitmaps.Clear();
        }

        // ── reacTIVision ───────────────────────────────────────────────────────
        private void LaunchReactivision()
        {
            if (_reactivisionProcess != null && _reactivisionProcess.HasExited)
                _reactivisionProcess = null;
            if (string.IsNullOrEmpty(AppConfig.ReactvisionExe)) return;
            if (_reactivisionProcess != null) return;
            try
            {
                Process[] already = Process.GetProcessesByName("reacTIVision");
                try
                {
                    foreach (var p in already)
                    {
                        try
                        {
                            if (!p.HasExited) return;
                        }
                        catch { }
                    }
                }
                finally
                {
                    foreach (var p in already)
                    {
                        try { p.Dispose(); } catch { }
                    }
                }

                var psi = new ProcessStartInfo(AppConfig.ReactvisionExe)
                {
                    WorkingDirectory = Path.GetDirectoryName(AppConfig.ReactvisionExe),
                    UseShellExecute = true,
                    WindowStyle = ProcessWindowStyle.Normal,
                };
                _reactivisionProcess = Process.Start(psi);
                Thread.Sleep(1500);
                if (_reactivisionProcess == null)
                {
                    MessageBox.Show(
                        "Failed to start reacTIVision process.",
                        "reacTIVision",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error);
                    return;
                }

                if (_reactivisionProcess.HasExited)
                {
                    MessageBox.Show(
                        "reacTIVision started then exited immediately.\n" +
                        $"Path: {AppConfig.ReactvisionExe}\n" +
                        $"Exit code: {_reactivisionProcess.ExitCode}",
                        "reacTIVision",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Warning);
                    _reactivisionProcess = null;
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "Could not launch reacTIVision.\n" +
                    $"Path: {AppConfig.ReactvisionExe}\n" +
                    $"Error: {ex.Message}",
                    "reacTIVision",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
        }

        private void StopReactivision()
        {
            if (_reactivisionProcess == null) return;
            try { _reactivisionProcess.Kill(); _reactivisionProcess.WaitForExit(3000); }
            catch { }
            _reactivisionProcess = null;
        }

        // ── TUIO callbacks ─────────────────────────────────────────────────────
        public void OnMarkerDetected(int fid)
        {
            if (!IsHandleCreated) return;
            if (InvokeRequired) { Invoke(new Action(() => OnMarkerDetected(fid))); return; }
            // Circular menu marker — allowed even while the game is running (same as Python).
            if (fid == AppConfig.MenuTuioMarker) { _menuOverlay?.ShowMenu(); return; }
            // Admin marker — even while Fruit Ninja is open; refresh BT and open admin if allowed.
            if (fid == AppConfig.AdminTuioMarker && !_adminMode)
            {
                _adminGate?.Refresh();
                if (_adminGate != null && _adminGate.IsConnected)
                {
                    _currentUser = null;
                    _adminNeutralY = null;
                    _adminSmoothedY = 0f;
                    _adminTriggered = false;
                    ShowAdminScreen();
                }
                else
                    MessageBox.Show(
                        "Bluetooth device not detected — admin locked.\n\n" +
                        $"Looking for: {AppConfig.AdminBluetoothName}\n" +
                        $"Gate log: {BluetoothAdminGate.LogPath}",
                        "Admin",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Warning);
                return;
            }
            if (_gameRunning) return;
            if (_adminMode) return;
            if (_currentUser == null && _users.ContainsKey(fid))
            { _currentUser = fid; ShowUserPage(fid); }
            else if (_currentUser == fid)
                SetTuioLight(true);
        }

        public void OnMarkerRemoved(int fid)
        {
            if (!IsHandleCreated) return;
            if (InvokeRequired) { Invoke(new Action(() => OnMarkerRemoved(fid))); return; }
            if (fid == AppConfig.MenuTuioMarker)
            {
                _menuOverlay?.HideMenu();
                _menuOverlay?.ResetMenuMarkerTracking();
                return;
            }
            if (fid == AppConfig.AdminTuioMarker && _adminMode)
            {
                _adminMode = false;
                ShowMainMenu();
                return;
            }
            if (_gameRunning) return;
            if (_currentUser == fid) SetTuioLight(false);
        }

        public void OnMarkerRotated(string direction, int fid)
        {
            if (!IsHandleCreated) return;
            if (InvokeRequired) { Invoke(new Action(() => OnMarkerRotated(direction, fid))); return; }
            if (_menuOverlay != null && _menuOverlay.IsActive) return;
            if (_adminMode && fid == AppConfig.AdminTuioMarker)
            {
                if (_adminTriggered)
                    return;
                _adminTriggered = true;
                if (direction == "left")
                {
                    _adminMode = false;
                    ShowMainMenu();
                }
                else
                    AdminRemoveSelected();
                return;
            }
            if (_gameRunning) return;
            if (_currentUser != fid || _rotationTriggered) return;
            _rotationTriggered = true;
            if (direction == "left") { _currentUser = null; ShowMainMenu(); }
            else DoLaunchGame();
        }

        // ── keyboard ──────────────────────────────────────────────────────────
        private void OnKeyDown(object sender, KeyEventArgs e)
        {
            switch (e.KeyCode)
            {
                case Keys.Escape:
                case Keys.Q: Close(); break;
                case Keys.F11:
                    WindowState = WindowState == FormWindowState.Maximized
                        ? FormWindowState.Normal : FormWindowState.Maximized; break;
                case Keys.D0: SimulateTuio(0); break;
                case Keys.D1: SimulateTuio(1); break;
                case Keys.D2: SimulateTuio(2); break;
                case Keys.D3: SimulateTuio(3); break;
                case Keys.M: SimulateMenuToggle(); break;
                case Keys.Left: SimulateRotation("left"); break;
                case Keys.Right: SimulateRotation("right"); break;
            }
        }

        private void SimulateTuio(int uid)
        {
            if (!_users.ContainsKey(uid)) return;
            _currentUser = uid;
            ShowUserPage(uid);
        }

        private void SimulateRotation(string dir)
        {
            if (_menuOverlay != null && _menuOverlay.IsActive) return;
            if (_gameRunning || _currentUser == null || _rotationTriggered) return;
            _rotationTriggered = true;
            if (dir == "left") { _currentUser = null; ShowMainMenu(); }
            else DoLaunchGame();
        }

        // ── menu toggle (M key) ────────────────────────────────────────────────
        private void SimulateMenuToggle()
        {
            if (_menuOverlay == null) return;
            if (_menuOverlay.IsActive) _menuOverlay.HideMenu();
            else _menuOverlay.ShowMenu();
        }

        // ── menu actions ───────────────────────────────────────────────────────
        private void MenuActionLeft() { TerminateGame(); }
        private void MenuActionRight() { }
        private void MenuActionRightUp() { }
        private void MenuActionRightDown() { }
        private void TerminateGame() { _gameRunning = false; }

        // ── screen helpers ─────────────────────────────────────────────────────
        private void ClearScreen()
        {
            _rotationTriggered = false;
            _tuioLight = null;
            _adminListFlow = null;
            _adminNeutralY = null;
            _adminSmoothedY = 0f;
            _adminTriggered = false;

            _blinkTimer?.Stop();
            _blinkTimer?.Dispose();
            _blinkTimer = null;
            _blinkLabel = null;

            _gifPlayer?.Dispose();
            _gifPlayer = null;
            _currentGifFrame = null;

            FreeScreenBitmaps();

            if (_screen != null)
            {
                Controls.Remove(_screen);
                _screen.Dispose();
                _screen = null;
            }
            GC.Collect();
        }

        private void SetTuioLight(bool active)
        {
            if (_tuioLight == null || _tuioLight.IsDisposed) return;
            _tuioLight.BackColor = active ? Color.Lime : Color.Red;
            _tuioLight.Invalidate();
        }

        private int SW => ClientSize.Width;
        private int SH => ClientSize.Height;

        // ═══════════════════════════════════════════════════════════════════════
        //  MAIN MENU
        // ═══════════════════════════════════════════════════════════════════════

        private void ShowMainMenu()
        {
            ClearScreen();
            int sw = SW, sh = SH;

            var root = new Panel { Bounds = ClientRectangle, BackColor = Color.Black };
            Controls.Add(root);
            root.BringToFront();
            _screen = root;
            root.Resize += (s, e) => { if (_screen == root) root.Bounds = ClientRectangle; };

            int cardW = (int)(sw * 0.130);
            int cardH = (int)(sh * 0.200);
            int gap = (int)(sw * 0.020);
            int totalW = _users.Count * cardW + (_users.Count - 1) * gap;
            int startX = sw / 2 - totalW / 2;
            int cardTop = (int)(sh * 0.570);
            int avSz = (int)(cardH * 0.48);

            var avatars = new Dictionary<int, Bitmap>();
            foreach (var kv in _users)
                avatars[kv.Key] = Track(AvatarHelper.Make(kv.Value.AvatarPath, avSz, kv.Value.Accent));

            int capSw = sw, capSh = sh;
            int capCardW = cardW, capCardH = cardH, capGap = gap;
            int capStartX = startX, capCardTop = cardTop, capAvSz = avSz;

            var canvas = new PaintCanvas { Bounds = root.ClientRectangle };
            root.Controls.Add(canvas);
            root.Resize += (s, e) =>
            {
                canvas.Bounds = root.ClientRectangle;
                canvas.Invalidate();
            };

            canvas.Paint += (s, e) =>
            {
                var g = e.Graphics;
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.InterpolationMode = InterpolationMode.HighQualityBicubic;

                if (_currentGifFrame != null)
                    g.DrawImage(_currentGifFrame, 0, 0, canvas.Width, canvas.Height);
                else
                    g.Clear(Color.Black);

                using var tf = new Font("Bahnschrift", capSh * 0.038f, FontStyle.Bold);
                using var tw = new SolidBrush(Color.White);
                string title = "GESTURE-POWERED  VIRTUAL  GAME  CONTROL";
                var tsz = g.MeasureString(title, tf);
                g.DrawString(title, tf, tw, (capSw - tsz.Width) / 2f, capSh * 0.17f);

                int lx = (int)(capSw * 0.225);
                using var sp = new Pen(Color.FromArgb(80, 80, 80), 2);
                g.DrawLine(sp, lx, (int)(capSh * 0.26f), capSw - lx, (int)(capSh * 0.26f));

                using var wf = new Font("Bahnschrift", capSh * 0.042f, FontStyle.Bold);
                using var wb = new SolidBrush(ColorTranslator.FromHtml("#00b4d8"));
                string wlc = "Welcome, User!";
                var wsz = g.MeasureString(wlc, wf);
                g.DrawString(wlc, wf, wb, (capSw - wsz.Width) / 2f, capSh * 0.34f);

                using var suf = new Font("Bahnschrift", capSh * 0.020f);
                using var sub = new SolidBrush(Color.FromArgb(170, 170, 170));
                string subTxt = "Please sign in by holding a TUIO marker in front of the camera.";
                var ssz = g.MeasureString(subTxt, suf);
                g.DrawString(subTxt, suf, sub, (capSw - ssz.Width) / 2f, capSh * 0.43f);

                using var hf = new Font("Consolas", capSh * 0.013f, FontStyle.Bold);
                using var hb = new SolidBrush(Color.FromArgb(85, 85, 85));
                string sec = "REGISTERED USERS";
                var secsz = g.MeasureString(sec, hf);
                g.DrawString(sec, hf, hb, (capSw - secsz.Width) / 2f, capSh * 0.530f);

                int ci = 0;
                foreach (var kv in _users)
                {
                    int uid = kv.Key;
                    var u = kv.Value;
                    int cx2 = capStartX + ci++ * (capCardW + capGap);
                    var av = avatars[uid];

                    using var cbg = new SolidBrush(u.HeaderBg);
                    g.FillRectangle(cbg, cx2, capCardTop, capCardW, capCardH);

                    int avX = cx2 + (capCardW - capAvSz) / 2;
                    int avY = capCardTop + (int)(capCardH * 0.06);
                    g.DrawImage(av, avX, avY, capAvSz, capAvSz);

                    using var mf2 = new Font("Consolas", capSh * 0.011f, FontStyle.Bold);
                    using var mb2 = new SolidBrush(u.Accent);
                    string mk = $"MARKER  #{uid}";
                    var mksz = g.MeasureString(mk, mf2);
                    float mkY = avY + capAvSz + (int)(capCardH * 0.04f);
                    g.DrawString(mk, mf2, mb2, cx2 + (capCardW - mksz.Width) / 2f, mkY);

                    using var nf2 = new Font("Bahnschrift", capSh * 0.018f, FontStyle.Bold);
                    using var nb2 = new SolidBrush(u.Fg);
                    var nmsz = g.MeasureString(u.Name, nf2);
                    g.DrawString(u.Name, nf2, nb2,
                                 cx2 + (capCardW - nmsz.Width) / 2f,
                                 mkY + mksz.Height + 2);

                    using var str = new SolidBrush(u.Accent);
                    g.FillRectangle(str, cx2, capCardTop + capCardH - 5, capCardW, 5);
                }
            };

            _blinkLabel = new Label
            {
                Text = "●  LISTENING FOR TUIO",
                Font = new Font("Consolas", sh * 0.016f),
                ForeColor = Color.Lime,
                BackColor = Color.Transparent,
                AutoSize = true,
                Top = (int)(sh * 0.855),
            };
            _blinkLabel.Left = (sw - _blinkLabel.PreferredWidth) / 2;
            canvas.Controls.Add(_blinkLabel);

            var btHud = new Label
            {
                Font = new Font("Consolas", sh * 0.014f, FontStyle.Bold),
                AutoSize = true,
                BackColor = Color.Transparent,
                Top = (int)(sh * 0.02),
                Left = (int)(sw * 0.02),
                Text = "BT: …",
                ForeColor = Color.Gainsboro,
            };
            canvas.Controls.Add(btHud);

            void UpdateBtHud()
            {
                if (btHud.IsDisposed) return;
                bool ok = _adminGate != null && _adminGate.IsConnected;
                string nm = _adminGate?.MatchedBluetoothName;
                btHud.ForeColor = ok ? Color.LimeGreen : Color.OrangeRed;
                btHud.Text = ok
                    ? $"BT admin ready — {nm}"
                    : $"BT admin locked — looking for \"{AppConfig.AdminBluetoothName}\"";
            }
            UpdateBtHud();

            _blinkState = true;
            _blinkTimer = new System.Windows.Forms.Timer { Interval = 650 };
            int tick = 0;
            _blinkTimer.Tick += (s, e) =>
            {
                if (_screen != root || _blinkLabel == null || _blinkLabel.IsDisposed)
                { _blinkTimer.Stop(); return; }
                _blinkState = !_blinkState;
                _blinkLabel.ForeColor = _blinkState ? Color.Lime : Color.FromArgb(0, 68, 0);
                if ((++tick & 3) == 0)
                {
                    _adminGate?.Refresh();
                    UpdateBtHud();
                }
            };
            _blinkTimer.Start();

            BeginInvoke(new Action(() =>
            {
                if (_screen != root) return;
                _gifPlayer = new GifPlayer(
                    AppConfig.GetAssetPath("mainbk.gif"),
                    frame =>
                    {
                        _currentGifFrame = frame;
                        if (!canvas.IsDisposed) canvas.Invalidate();
                    });
            }));
        }

        // ═══════════════════════════════════════════════════════════════════════
        //  USER PAGE
        // ═══════════════════════════════════════════════════════════════════════

        private void ShowUserPage(int userId)
        {
            ClearScreen();
            var u = _users[userId];
            int sw = SW, sh = SH;

            var root = new Panel { Bounds = ClientRectangle, BackColor = u.Bg };
            Controls.Add(root);
            root.BringToFront();
            _screen = root;
            root.Resize += (s, e) => { if (_screen == root) root.Bounds = ClientRectangle; };

            // ── HEADER ────────────────────────────────────────────────────────
            int hdrH = (int)(sh * 0.10);
            var header = new Panel { Bounds = new Rectangle(0, 0, sw, hdrH), BackColor = u.HeaderBg };
            root.Controls.Add(header);

            var titleLbl = new Label
            {
                Text = "  GESTURE-POWERED  VIRTUAL  GAME  CONTROL",
                Font = new Font("Bahnschrift", sh * 0.020f, FontStyle.Bold),
                ForeColor = u.Accent,
                BackColor = Color.Transparent,
                AutoSize = true,
            };
            titleLbl.Top = (hdrH - titleLbl.PreferredHeight) / 2;
            titleLbl.Left = (int)(sw * 0.022);
            header.Controls.Add(titleLbl);

            int dotSz = (int)(hdrH * 0.36);
            var dot = new Panel { Size = new Size(dotSz, dotSz), BackColor = Color.Lime };
            dot.Paint += (s, e) =>
            {
                e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
                using var b = new SolidBrush(dot.BackColor);
                e.Graphics.FillEllipse(b, 0, 0, dot.Width - 1, dot.Height - 1);
                using var p = new Pen(Color.FromArgb(0, 85, 0), 2);
                e.Graphics.DrawEllipse(p, 1, 1, dot.Width - 3, dot.Height - 3);
            };
            dot.BackColorChanged += (s, e) => dot.Invalidate();

            var tuioLbl = new Label
            {
                Text = "TUIO READING",
                Font = new Font("Consolas", sh * 0.014f, FontStyle.Bold),
                ForeColor = Color.FromArgb(170, 170, 170),
                BackColor = Color.Transparent,
                AutoSize = true,
            };
            int groupW = dotSz + 8 + tuioLbl.PreferredWidth;
            int groupX = sw - (int)(sw * 0.030) - groupW;
            dot.Location = new Point(groupX, (hdrH - dotSz) / 2);
            tuioLbl.Location = new Point(groupX + dotSz + 8, (hdrH - tuioLbl.PreferredHeight) / 2);
            header.Controls.Add(dot);
            header.Controls.Add(tuioLbl);
            _tuioLight = dot;

            // ── GAME BAR ──────────────────────────────────────────────────────
            int barH = (int)(sh * 0.22);
            var gameBar = new Panel { Bounds = new Rectangle(0, sh - barH, sw, barH), BackColor = u.HeaderBg };
            root.Controls.Add(gameBar);

            int btnPadY = (int)(barH * 0.14);
            int btnPadX = (int)(sw * 0.010);
            int hintW = (int)(sw * 0.30);

            gameBar.Controls.Add(BuildHintBox(
                new Rectangle(btnPadX, btnPadY, hintW, barH - btnPadY * 2),
                u.Bg, u.Accent,
                "◄  ROTATE LEFT", Color.White, "Back to Main Menu", Color.FromArgb(170, 170, 170), sh));

            gameBar.Controls.Add(BuildHintBox(
                new Rectangle(btnPadX * 2 + hintW, btnPadY, hintW, barH - btnPadY * 2),
                u.Glow, u.Accent,
                "ROTATE RIGHT  ►", u.HeaderBg, "Launch Ninja Fruit", u.Bg, sh));

            int iconSz = (int)(barH * 0.62);
            var iconWrapper = new Panel
            {
                BackColor = u.HeaderBg,
                Bounds = new Rectangle(
                    sw - (int)(sw * 0.032) - iconSz - 10,
                    (barH - iconSz - 28) / 2,
                    iconSz + 10, iconSz + 28),
            };
            iconWrapper.Controls.Add(new Label
            {
                Text = "NINJA FRUIT",
                Font = new Font("Bahnschrift", sh * 0.018f, FontStyle.Bold),
                ForeColor = u.Accent,
                BackColor = Color.Transparent,
                TextAlign = ContentAlignment.MiddleCenter,
                Bounds = new Rectangle(0, 0, iconWrapper.Width, 24),
            });
            var iconPb = new PictureBox
            {
                Bounds = new Rectangle(3, 26, iconSz, iconSz),
                SizeMode = PictureBoxSizeMode.StretchImage,
                BackColor = u.Accent,
            };
            string iconPath = AppConfig.GetAssetPath("Fruit_Ninja_logo.png");
            if (File.Exists(iconPath))
            {
                try
                {
                    byte[] ib = File.ReadAllBytes(iconPath);
                    using var ims = new MemoryStream(ib);
                    iconPb.Image = new Bitmap(Image.FromStream(ims));
                }
                catch { }
            }
            iconWrapper.Controls.Add(iconPb);
            gameBar.Controls.Add(iconWrapper);

            // ── BODY ──────────────────────────────────────────────────────────
            int bodyH = sh - hdrH - barH;
            var body = new Panel { Bounds = new Rectangle(0, hdrH, sw, bodyH), BackColor = u.Bg };
            root.Controls.Add(body);

            int avSz = (int)(bodyH * 0.38);
            Bitmap avBmp = Track(AvatarHelper.Make(u.AvatarPath, avSz, u.Accent));

            var capU = u;
            Bitmap capAv = avBmp;
            int capAvSz = avSz;
            int capUid = userId;
            int capSw = sw;
            int capSh = sh;
            int capBodyH = bodyH;

            var canvas = new PaintCanvas { Bounds = body.ClientRectangle };
            body.Controls.Add(canvas);
            body.Resize += (s, e) =>
            {
                canvas.Bounds = body.ClientRectangle;
                canvas.Invalidate();
            };

            canvas.Paint += (s, e) =>
            {
                var g = e.Graphics;
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.InterpolationMode = InterpolationMode.HighQualityBicubic;

                if (_currentGifFrame != null)
                    g.DrawImage(_currentGifFrame, 0, 0, canvas.Width, canvas.Height);
                else
                    g.Clear(capU.Bg);

                g.DrawImage(capAv,
                            (capSw - capAvSz) / 2,
                            (int)(capBodyH * 0.04),
                            capAvSz, capAvSz);

                using var wf = new Font("Bahnschrift", capSh * 0.035f);
                using var wb = new SolidBrush(capU.Fg);
                var wsz = g.MeasureString("Welcome,", wf);
                g.DrawString("Welcome,", wf, wb, (capSw - wsz.Width) / 2f, capBodyH * 0.47f);

                using var nf = new Font("Impact", capSh * 0.088f, FontStyle.Bold);
                using var nb = new SolidBrush(capU.Accent);
                var nsz = g.MeasureString(capU.Name, nf);
                g.DrawString(capU.Name, nf, nb, (capSw - nsz.Width) / 2f, capBodyH * 0.59f);

                using var mf = new Font("Consolas", capSh * 0.015f);
                using var mg = new SolidBrush(capU.Glow);
                string mt = $"TUIO marker  #{capUid}  recognised";
                var msz = g.MeasureString(mt, mf);
                g.DrawString(mt, mf, mg, (capSw - msz.Width) / 2f, capBodyH * 0.76f);

                int dw = (int)(capSw * 0.40), dx = (capSw - dw) / 2, dy = (int)(capBodyH * 0.855);
                using var db = new SolidBrush(capU.Accent);
                g.FillRectangle(db, dx, dy, dw, 4);
            };

            BeginInvoke(new Action(() =>
            {
                if (_screen != root) return;
                _gifPlayer = new GifPlayer(u.GifPath, frame =>
                {
                    _currentGifFrame = frame;
                    if (!canvas.IsDisposed) canvas.Invalidate();
                });
            }));
        }

        // ── hint box ───────────────────────────────────────────────────────────
        private static Panel BuildHintBox(
            Rectangle bounds, Color bg, Color accent,
            string mainText, Color mainColor,
            string subText, Color subColor, int sh)
        {
            var box = new Panel { Bounds = bounds, BackColor = bg };
            box.Paint += (s, e) =>
            {
                using var ab = new SolidBrush(accent);
                e.Graphics.FillRectangle(ab, 0, 0, box.Width, 5);
                e.Graphics.FillRectangle(ab, 0, box.Height - 2, box.Width, 2);
            };

            var mainLbl = new Label
            {
                Text = mainText,
                Font = new Font("Bahnschrift", sh * 0.025f, FontStyle.Bold),
                ForeColor = mainColor,
                BackColor = Color.Transparent,
                AutoSize = true,
            };
            mainLbl.Top = bounds.Height / 2 - mainLbl.PreferredHeight;
            mainLbl.Left = (bounds.Width - mainLbl.PreferredWidth) / 2;
            box.Controls.Add(mainLbl);

            var subLbl = new Label
            {
                Text = subText,
                Font = new Font("Consolas", sh * 0.013f),
                ForeColor = subColor,
                BackColor = Color.Transparent,
                AutoSize = true,
            };
            subLbl.Top = mainLbl.Top + mainLbl.PreferredHeight + 4;
            subLbl.Left = (bounds.Width - subLbl.PreferredWidth) / 2;
            box.Controls.Add(subLbl);

            return box;
        }

        // ═══════════════════════════════════════════════════════════════════════
        //  ADMIN SCREEN
        // ═══════════════════════════════════════════════════════════════════════
        private void ShowAdminScreen()
        {
            _adminMode = true;
            _adminSelected = 0;
            _adminNeutralY = null;
            _adminSmoothedY = 0f;
            _adminTriggered = false;

            ClearScreen();
            int sw = SW, sh = SH;
            int marginX = (int)(sw * 0.06);

            var root = new Panel { Bounds = ClientRectangle, BackColor = Color.FromArgb(10, 10, 26) };
            Controls.Add(root);
            root.BringToFront();
            _screen = root;

            var header = new Panel
            {
                Bounds = new Rectangle(0, 0, sw, (int)(sh * 0.10)),
                BackColor = Color.FromArgb(26, 26, 58)
            };
            root.Controls.Add(header);

            var title = new Label
            {
                Text = "  ADMIN PANEL",
                Font = new Font("Bahnschrift", sh * 0.03f, FontStyle.Bold),
                ForeColor = Color.Orange,
                BackColor = Color.Transparent,
                AutoSize = true,
                Left = (int)(sw * 0.02),
                Top = (int)(sh * 0.02)
            };
            header.Controls.Add(title);

            string btText;
            if (_adminGate != null && _adminGate.IsConnected)
            {
                string n = _adminGate.MatchedBluetoothName;
                btText = string.IsNullOrWhiteSpace(n) ? "BT DEVICE DETECTED" : $"BT: {n}";
            }
            else
                btText = "BT DEVICE OFFLINE";
            var bt = new Label
            {
                Text = btText,
                Font = new Font("Consolas", sh * 0.015f, FontStyle.Bold),
                ForeColor = (_adminGate != null && _adminGate.IsConnected) ? Color.LimeGreen : Color.OrangeRed,
                BackColor = Color.Transparent,
                AutoSize = true,
                Left = sw - (int)(sw * 0.30),
                Top = (int)(sh * 0.03)
            };
            header.Controls.Add(bt);

            int y = (int)(sh * 0.11);
            foreach (string line in new[]
                     {
                         "Move marker UP / DOWN to scroll users",
                         "Push marker RIGHT to add a user",
                         "Rotate marker RIGHT to remove selected",
                         "Rotate marker LEFT to go back",
                         "Remove admin marker to return to main menu",
                     })
            {
                var ln = new Label
                {
                    Text = line,
                    Font = new Font("Consolas", sh * 0.015f),
                    ForeColor = Color.FromArgb(102, 102, 153),
                    BackColor = Color.Transparent,
                    AutoSize = true,
                    Left = marginX,
                    Top = y,
                };
                root.Controls.Add(ln);
                y += ln.Height + 4;
            }

            y += 6;
            var sep = new Panel
            {
                Bounds = new Rectangle(marginX, y, sw - 2 * marginX, 2),
                BackColor = Color.FromArgb(51, 51, 102),
            };
            root.Controls.Add(sep);
            y += 12;

            _adminListFlow = new FlowLayoutPanel
            {
                Location = new Point(marginX, y),
                Size = new Size(sw - 2 * marginX, Math.Max(80, sh - y - 16)),
                Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right,
                AutoScroll = true,
                FlowDirection = FlowDirection.TopDown,
                WrapContents = false,
                BackColor = Color.FromArgb(10, 10, 26),
            };
            root.Controls.Add(_adminListFlow);

            root.Resize += AdminRootResize;
            RebuildAdminList();
        }

        private void AdminRootResize(object sender, EventArgs e)
        {
            if (sender is not Panel root || _screen != root || _adminListFlow == null) return;
            int sh = root.ClientSize.Height;
            int sw = root.ClientSize.Width;
            int marginX = (int)(sw * 0.06);
            int y = _adminListFlow.Top;
            _adminListFlow.Width = Math.Max(60, sw - 2 * marginX);
            _adminListFlow.Height = Math.Max(80, sh - y - 16);
            int w = Math.Max(60, _adminListFlow.ClientSize.Width - 24);
            foreach (Control c in _adminListFlow.Controls)
                c.Width = w;
        }

        private void RebuildAdminList()
        {
            if (_adminListFlow == null || _adminListFlow.IsDisposed) return;
            int n = _users.Count;
            if (n == 0)
                _adminSelected = 0;
            else
                _adminSelected = Math.Max(0, Math.Min(_adminSelected, n - 1));

            int sh = ClientSize.Height;
            int rowW = Math.Max(60, _adminListFlow.ClientSize.Width - 24);

            _adminListFlow.SuspendLayout();
            _adminListFlow.Controls.Clear();

            int idx = 0;
            foreach (var kv in _users.OrderBy(k => k.Key))
            {
                bool sel = idx == _adminSelected;
                var row = new Panel
                {
                    Height = Math.Max(44, (int)(sh * 0.072)),
                    Width = rowW,
                    Margin = new Padding(3),
                    BackColor = sel ? Color.FromArgb(42, 42, 90) : Color.FromArgb(17, 17, 51),
                };
                if (sel)
                {
                    row.Paint += (s, pe) =>
                    {
                        using var pen = new Pen(Color.FromArgb(255, 153, 0), 2);
                        pe.Graphics.DrawRectangle(pen, 1, 1, row.Width - 3, row.Height - 3);
                    };
                }

                var lbl = new Label
                {
                    Text = $"  MARKER #{kv.Key}   {kv.Value.Name}",
                    Font = new Font("Bahnschrift", sh * 0.022f, sel ? FontStyle.Bold : FontStyle.Regular),
                    ForeColor = sel ? Color.White : Color.FromArgb(170, 170, 204),
                    BackColor = Color.Transparent,
                    AutoSize = false,
                    Dock = DockStyle.Fill,
                    TextAlign = ContentAlignment.MiddleLeft,
                    Padding = new Padding(16, 0, 0, 0),
                };
                row.Controls.Add(lbl);
                if (sel)
                {
                    var tag = new Label
                    {
                        Text = "<< SELECTED >>",
                        AutoSize = true,
                        ForeColor = Color.FromArgb(255, 153, 0),
                        BackColor = Color.Transparent,
                        Dock = DockStyle.Right,
                        TextAlign = ContentAlignment.MiddleRight,
                        Padding = new Padding(0, 0, 16, 0),
                    };
                    row.Controls.Add(tag);
                }

                _adminListFlow.Controls.Add(row);
                idx++;
            }

            _adminListFlow.ResumeLayout();
        }

        private void OnTuioMarkerMoved(int fid, float x, float y, float angleRad)
        {
            if (!IsHandleCreated) return;
            if (InvokeRequired)
            {
                try { BeginInvoke(new Action(() => OnTuioMarkerMoved(fid, x, y, angleRad))); } catch { }
                return;
            }

            if (_gameRunning && _activeGameForm != null && !_activeGameForm.IsDisposed &&
                _currentUser.HasValue && fid == _currentUser.Value && _users.ContainsKey(fid))
            {
                _activeGameForm.FeedTuioPointer(x, y);
                return;
            }

            _menuOverlay?.FeedMenuMarkerAngle(fid, angleRad);

            if (_adminMode && fid == AppConfig.AdminTuioMarker)
                AdminMarkerMoved(x, y);
        }

        private void AdminMarkerMoved(float x, float y)
        {
            if (!_adminMode || _adminListFlow == null) return;

            float th = AppConfig.MenuMotionThresh;
            float alpha = AppConfig.MenuSmoothAlpha;
            alpha = Math.Clamp(alpha, 0.05f, 0.95f);

            if (_adminNeutralY == null)
            {
                _adminNeutralY = y;
                _adminSmoothedY = y;
                return;
            }

            _adminSmoothedY = alpha * _adminSmoothedY + (1f - alpha) * y;
            float dy = _adminSmoothedY - _adminNeutralY.Value;

            if (dy < -th * 1.5f && !_adminTriggered)
            {
                _adminNeutralY = _adminSmoothedY;
                int c = _users.Count;
                _adminSelected = c > 0 ? Math.Max(0, _adminSelected - 1) : 0;
                RebuildAdminList();
            }
            else if (dy > th * 1.5f && !_adminTriggered)
            {
                _adminNeutralY = _adminSmoothedY;
                int c = _users.Count;
                _adminSelected = c > 0 ? Math.Min(c - 1, _adminSelected + 1) : 0;
                RebuildAdminList();
            }

            if (x > 0.65f && !_adminTriggered)
            {
                _adminTriggered = true;
                AdminAddUser();
            }
            else if (x < 0.55f)
                _adminTriggered = false;
        }

        private void AdminAddUser()
        {
            int newId = UserStore.NextFreeMarkerId(_users);
            string newName = UserStore.RandomDisplayName();
            _users[newId] = CharacterMap.BuildUserProfile(newId, newName);
            UserStore.SaveUsers(_users);
            var keys = _users.Keys.OrderBy(k => k).ToList();
            _adminSelected = keys.IndexOf(newId);
            if (_adminSelected < 0) _adminSelected = Math.Max(0, keys.Count - 1);
            RebuildAdminList();
        }

        private void AdminRemoveSelected()
        {
            var keys = _users.Keys.OrderBy(k => k).ToList();
            if (keys.Count == 0)
            {
                _adminTriggered = false;
                return;
            }

            int idx = Math.Min(_adminSelected, keys.Count - 1);
            int uid = keys[idx];
            _users.Remove(uid);
            UserStore.SaveUsers(_users);
            _adminSelected = Math.Max(0, idx - 1);
            RebuildAdminList();
            _adminTriggered = false;
        }

        // ═══════════════════════════════════════════════════════════════════════
        //  GAME LAUNCH
        // ═══════════════════════════════════════════════════════════════════════

        private void DoLaunchGame()
        {
            string name = _currentUser.HasValue ? _users[_currentUser.Value].Name : "";
            // Keep reacTIVision/TUIO for every user so in-game pointer tracks the same marker as the mouse.
            _useTuioControl = _currentUser.HasValue && _users.ContainsKey(_currentUser.Value);

            if (!_useTuioControl) { StopReactivision(); Thread.Sleep(2000); }

            bool success = LaunchGame(name, out string errMsg);
            if (success)
            {
                _gameRunning = true;
                WindowState = FormWindowState.Minimized;
                _rotationTriggered = false;
                var t = new System.Windows.Forms.Timer { Interval = 1000 };
                t.Tick += CheckGameExit;
                t.Start();
            }
            else
            {
                _rotationTriggered = false;
                ShowError(errMsg);
            }
        }

        private bool LaunchGame(string characterName, out string errorMsg)
        {
            errorMsg = "";
            try
            {
                var gameForm = new Form1(); // FruitNinjaGame.Form1 — the actual game
                _activeGameForm = gameForm;
                gameForm.FormClosed += (s, e) =>
                {
                    _gameRunning = false;
                    if (ReferenceEquals(_activeGameForm, gameForm))
                        _activeGameForm = null;
                };
                gameForm.Show();
                return true;
            }
            catch (Exception ex)
            {
                errorMsg = ex.Message;
                return false;
            }
        }

        private void CheckGameExit(object sender, EventArgs e)
        {
            if (_gameRunning) return;
            ((System.Windows.Forms.Timer)sender).Stop();
            LaunchReactivision();
            WindowState = FormWindowState.Maximized;
        }

        private void ShowError(string message)
        {
            if (_screen == null || _screen.IsDisposed) return;
            var overlay = new Panel
            {
                BackColor = Color.FromArgb(210, 15, 15, 15),
                Bounds = new Rectangle(
                    (int)(SW * 0.10), (int)(SH * 0.35),
                    (int)(SW * 0.80), (int)(SH * 0.25)),
            };
            overlay.Controls.Add(new Label
            {
                Text = $"⚠  {message}",
                Font = new Font("Courier New", SH * 0.018f),
                ForeColor = Color.FromArgb(255, 85, 85),
                BackColor = Color.Transparent,
                TextAlign = ContentAlignment.MiddleCenter,
                Dock = DockStyle.Fill,
            });
            _screen.Controls.Add(overlay);
            overlay.BringToFront();
        }
    }
}