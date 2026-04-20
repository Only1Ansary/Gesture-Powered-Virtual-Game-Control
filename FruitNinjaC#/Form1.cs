#nullable disable
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Threading;
using System.Diagnostics;
using System.Windows.Forms;

namespace NinjaFruit
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
        public static readonly string BaseDir = AppDomain.CurrentDomain.BaseDirectory;
        public static readonly string ReactvisionExe = "";
        public static readonly string TuioHost = "127.0.0.1";
        public static readonly int TuioPort = 3333;
        public static readonly bool VrBridgeEnabled = false;
        public static readonly int MenuTuioMarker = 10;
        public static readonly float MenuVolumeStep = 5f;
        public static readonly double MenuVolRepeatSec = 0.4;
        public static readonly double MenuActionCooldown = 0.6;
        public static readonly float MenuMotionThresh = 0.015f;
        public static readonly float MenuSmoothAlpha = 0.25f;
        public static readonly float MenuCursorGain = 2.5f;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    //  CHARACTER MAP
    // ═══════════════════════════════════════════════════════════════════════════

    public static class CharacterMap
    {
        public static Dictionary<int, UserProfile> GetAllUsers()
        {
            string assets = Path.Combine(AppConfig.BaseDir, "assets");
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
                    AvatarPath = Path.Combine(assets, "blue user.jpg"),
                    GifPath = Path.Combine(assets, "blue animation.gif"),
                },
                [1] = new UserProfile
                {
                    Name = "Rogue",
                    Bg = ColorTranslator.FromHtml("#0e0a1a"),
                    HeaderBg = ColorTranslator.FromHtml("#1a0d2e"),
                    Accent = ColorTranslator.FromHtml("#9d4edd"),
                    Fg = Color.White,
                    Glow = ColorTranslator.FromHtml("#c77dff"),
                    AvatarPath = Path.Combine(assets, "purple user.jpg"),
                    GifPath = Path.Combine(assets, "purple animation.gif"),
                },
                [2] = new UserProfile
                {
                    Name = "Ditto",
                    Bg = ColorTranslator.FromHtml("#0a1a0e"),
                    HeaderBg = ColorTranslator.FromHtml("#0d2a13"),
                    Accent = ColorTranslator.FromHtml("#57cc99"),
                    Fg = Color.White,
                    Glow = ColorTranslator.FromHtml("#80ed99"),
                    AvatarPath = Path.Combine(assets, "green user.jpg"),
                    GifPath = Path.Combine(assets, "green animation.gif"),
                },
                [3] = new UserProfile
                {
                    Name = "Arthur",
                    Bg = ColorTranslator.FromHtml("#1a0a0a"),
                    HeaderBg = ColorTranslator.FromHtml("#2a0d0d"),
                    Accent = ColorTranslator.FromHtml("#ff6b6b"),
                    Fg = Color.White,
                    Glow = ColorTranslator.FromHtml("#ff9e9e"),
                    AvatarPath = Path.Combine(assets, "orange user.jpg"),
                    GifPath = Path.Combine(assets, "orange animation.gif"),
                },
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

            // Fire first frame immediately so there is no blank flash
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
    // ═══════════════════════════════════════════════════════════════════════════

    public class CircularMenuOverlay : PaintCanvas
    {
        public bool IsActive { get; private set; }

        private readonly Action _onLeft, _onRight, _onRightUp, _onRightDown;
        private readonly Action _onVolUp, _onVolDown;

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

            Visible = false;
            parent.Controls.Add(this);
            BringToFront();
        }

        public void ShowMenu() { IsActive = true; Visible = true; BringToFront(); Invalidate(); }
        public void HideMenu() { IsActive = false; Visible = false; }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            int cx = Width / 2, cy = Height / 2;
            int r = Math.Min(Width, Height) / 3;

            using var dim = new SolidBrush(Color.FromArgb(160, 0, 0, 0));
            g.FillRectangle(dim, 0, 0, Width, Height);

            DrawSlice(g, cx, cy, r, -90, 90, "◄ TERMINATE", Color.FromArgb(180, 220, 50, 50));
            DrawSlice(g, cx, cy, r, 0, 90, "▲ MIN GAME", Color.FromArgb(130, 100, 100, 200));
            DrawSlice(g, cx, cy, r, 90, 90, "MINIMIZE ►", Color.FromArgb(180, 0, 180, 216));
            DrawSlice(g, cx, cy, r, 180, 90, "▼ SHOW GAME", Color.FromArgb(130, 50, 200, 100));

            using var rp = new Pen(Color.FromArgb(200, 0, 180, 216), 3);
            g.DrawEllipse(rp, cx - r, cy - r, r * 2, r * 2);

            using var cf = new Font("Consolas", 11, FontStyle.Bold);
            using var cb = new SolidBrush(Color.White);
            var csz = g.MeasureString("MENU", cf);
            g.DrawString("MENU", cf, cb, cx - csz.Width / 2, cy - csz.Height / 2);
        }

        private static void DrawSlice(Graphics g, int cx, int cy, int r,
                                      float start, float sweep, string label, Color col)
        {
            using var path = new GraphicsPath();
            path.AddPie(cx - r, cy - r, r * 2, r * 2, start, sweep);
            using var brush = new SolidBrush(col);
            g.FillPath(brush, path);

            double mid = (start + sweep / 2.0) * Math.PI / 180.0;
            float tx = cx + r * 0.65f * (float)Math.Cos(mid);
            float ty = cy + r * 0.65f * (float)Math.Sin(mid);
            using var f = new Font("Consolas", 9, FontStyle.Bold);
            using var b = new SolidBrush(Color.White);
            var sz = g.MeasureString(label, f);
            g.DrawString(label, f, b, tx - sz.Width / 2, ty - sz.Height / 2);
        }

        protected override void OnMouseClick(MouseEventArgs e)
        {
            int cx = Width / 2, cy = Height / 2;
            double angle = Math.Atan2(e.Y - cy, e.X - cx) * 180.0 / Math.PI;
            if (angle < 0) angle += 360;

            if (angle >= 270 || angle < 90) _onLeft?.Invoke();
            else if (angle >= 90 && angle < 180) _onRightDown?.Invoke();
            else if (angle >= 180 && angle < 270) _onRight?.Invoke();
            else _onRightUp?.Invoke();
        }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    //  FORM1
    // ═══════════════════════════════════════════════════════════════════════════

    public partial class Form1 : Form
    {
        private readonly Dictionary<int, UserProfile> _users;
        private int? _currentUser = null;
        private bool _rotationTriggered = false;
        private bool _useTuioControl = false;
        private Control _screen = null;
        private GifPlayer _gifPlayer = null;
        private Bitmap _currentGifFrame = null;   // ← current GIF frame
        private Panel _tuioLight = null;
        private Process _reactivisionProcess = null;
        private bool _gameRunning = false;

        private readonly List<Bitmap> _screenBitmaps = new List<Bitmap>();
        private readonly HashSet<int> _tuioControlUsers = new HashSet<int> { 0, 1 };

        private System.Windows.Forms.Timer _blinkTimer = null;
        private Label _blinkLabel = null;
        private bool _blinkState = true;

        private CircularMenuOverlay _menuOverlay = null;

        // ── ctor ───────────────────────────────────────────────────────────────
        public Form1()
        {
            InitializeComponent();

            _users = CharacterMap.GetAllUsers();

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
                if (_menuOverlay != null) _menuOverlay.Bounds = ClientRectangle;
            };
        }

        // ── load ───────────────────────────────────────────────────────────────
        private void OnFormLoad(object sender, EventArgs e)
        {
            _menuOverlay = new CircularMenuOverlay(
                this,
                onLeft: MenuActionLeft,
                onRight: MenuActionRight,
                onRightUp: MenuActionRightUp,
                onRightDown: MenuActionRightDown,
                onVolUp: () => { },
                onVolDown: () => { }
            );
            _menuOverlay.Bounds = ClientRectangle;

            LaunchReactivision();
            ShowMainMenu();
        }

        // ── exit ───────────────────────────────────────────────────────────────
        private void OnAppExit()
        {
            StopReactivision();
            _blinkTimer?.Stop();
            _gifPlayer?.Dispose();
            FreeScreenBitmaps();
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
            if (_reactivisionProcess != null || string.IsNullOrEmpty(AppConfig.ReactvisionExe)) return;
            try
            {
                var psi = new ProcessStartInfo(AppConfig.ReactvisionExe)
                {
                    WorkingDirectory = Path.GetDirectoryName(AppConfig.ReactvisionExe),
                    WindowStyle = ProcessWindowStyle.Minimized,
                };
                _reactivisionProcess = Process.Start(psi);
                Thread.Sleep(1500);
            }
            catch (Exception ex) { Console.WriteLine($"[ERROR] {ex.Message}"); }
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
            if (fid == AppConfig.MenuTuioMarker) { _menuOverlay?.ShowMenu(); return; }
            if (_gameRunning) return;
            if (_currentUser == null && _users.ContainsKey(fid))
            { _currentUser = fid; ShowUserPage(fid); }
            else if (_currentUser == fid)
                SetTuioLight(true);
        }

        public void OnMarkerRemoved(int fid)
        {
            if (!IsHandleCreated) return;
            if (InvokeRequired) { Invoke(new Action(() => OnMarkerRemoved(fid))); return; }
            if (fid == AppConfig.MenuTuioMarker) { _menuOverlay?.HideMenu(); return; }
            if (_gameRunning) return;
            if (_currentUser == fid) SetTuioLight(false);
        }

        public void OnMarkerRotated(string direction, int fid)
        {
            if (!IsHandleCreated) return;
            if (InvokeRequired) { Invoke(new Action(() => OnMarkerRotated(direction, fid))); return; }
            if (_menuOverlay != null && _menuOverlay.IsActive) return;
            if (_gameRunning || _currentUser != fid || _rotationTriggered) return;
            _rotationTriggered = true;
            if (direction == "left") { _currentUser = null; ShowMainMenu(); }
            else DoLaunchGame();
        }

        // ── keyboard simulation ────────────────────────────────────────────────
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

            _blinkTimer?.Stop();
            _blinkTimer?.Dispose();
            _blinkTimer = null;
            _blinkLabel = null;

            _gifPlayer?.Dispose();
            _gifPlayer = null;
            _currentGifFrame = null;    // ← clear stale frame

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

            // Pre-build avatar bitmaps
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

            // Single PaintCanvas — GIF frame first, then all UI on top
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

                // 1. GIF background
                if (_currentGifFrame != null)
                    g.DrawImage(_currentGifFrame, 0, 0, canvas.Width, canvas.Height);
                else
                    g.Clear(Color.Black);

                // 2. Title
                using var tf = new Font("Bahnschrift", capSh * 0.038f, FontStyle.Bold);
                using var tw = new SolidBrush(Color.White);
                string title = "GESTURE-POWERED  VIRTUAL  GAME  CONTROL";
                var tsz = g.MeasureString(title, tf);
                g.DrawString(title, tf, tw, (capSw - tsz.Width) / 2f, capSh * 0.17f);

                // 3. Divider line
                int lx = (int)(capSw * 0.225);
                using var sp = new Pen(Color.FromArgb(80, 80, 80), 2);
                g.DrawLine(sp, lx, (int)(capSh * 0.26f), capSw - lx, (int)(capSh * 0.26f));

                // 4. Welcome text
                using var wf = new Font("Bahnschrift", capSh * 0.042f, FontStyle.Bold);
                using var wb = new SolidBrush(ColorTranslator.FromHtml("#00b4d8"));
                string wlc = "Welcome, User!";
                var wsz = g.MeasureString(wlc, wf);
                g.DrawString(wlc, wf, wb, (capSw - wsz.Width) / 2f, capSh * 0.34f);

                // 5. Sub-text
                using var suf = new Font("Bahnschrift", capSh * 0.020f);
                using var sub = new SolidBrush(Color.FromArgb(170, 170, 170));
                string subTxt = "Please sign in by holding a TUIO marker in front of the camera.";
                var ssz = g.MeasureString(subTxt, suf);
                g.DrawString(subTxt, suf, sub, (capSw - ssz.Width) / 2f, capSh * 0.43f);

                // 6. Section heading
                using var hf = new Font("Consolas", capSh * 0.013f, FontStyle.Bold);
                using var hb = new SolidBrush(Color.FromArgb(85, 85, 85));
                string sec = "REGISTERED USERS";
                var secsz = g.MeasureString(sec, hf);
                g.DrawString(sec, hf, hb, (capSw - secsz.Width) / 2f, capSh * 0.530f);

                // 7. User cards
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

            // Blink label
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

            _blinkState = true;
            _blinkTimer = new System.Windows.Forms.Timer { Interval = 650 };
            _blinkTimer.Tick += (s, e) =>
            {
                if (_screen != root || _blinkLabel == null || _blinkLabel.IsDisposed)
                { _blinkTimer.Stop(); return; }
                _blinkState = !_blinkState;
                _blinkLabel.ForeColor = _blinkState ? Color.Lime : Color.FromArgb(0, 68, 0);
            };
            _blinkTimer.Start();

            // Start GIF
            BeginInvoke(new Action(() =>
            {
                if (_screen != root) return;
                _gifPlayer = new GifPlayer(
                    Path.Combine(AppConfig.BaseDir, "assets", "mainbk.gif"),
                    frame =>
                    {
                        _currentGifFrame = frame;
                        if (!canvas.IsDisposed) canvas.Invalidate();
                    });
            }));

            if (_menuOverlay != null) { _menuOverlay.Bounds = ClientRectangle; _menuOverlay.BringToFront(); }
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
            string iconPath = Path.Combine(AppConfig.BaseDir, "assets", "Fruit_Ninja_logo.png");
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

            // Pre-build avatar
            int avSz = (int)(bodyH * 0.38);
            Bitmap avBmp = Track(AvatarHelper.Make(u.AvatarPath, avSz, u.Accent));

            // Capture locals for Paint lambda
            var capU = u;
            Bitmap capAv = avBmp;
            int capAvSz = avSz;
            int capUid = userId;
            int capSw = sw;
            int capSh = sh;
            int capBodyH = bodyH;

            // Single PaintCanvas — GIF first, overlays on top
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

                // 1. GIF background
                if (_currentGifFrame != null)
                    g.DrawImage(_currentGifFrame, 0, 0, canvas.Width, canvas.Height);
                else
                    g.Clear(capU.Bg);

                // 2. Avatar
                g.DrawImage(capAv,
                            (capSw - capAvSz) / 2,
                            (int)(capBodyH * 0.04),
                            capAvSz, capAvSz);

                // 3. "Welcome,"
                using var wf = new Font("Bahnschrift", capSh * 0.035f);
                using var wb = new SolidBrush(capU.Fg);
                var wsz = g.MeasureString("Welcome,", wf);
                g.DrawString("Welcome,", wf, wb, (capSw - wsz.Width) / 2f, capBodyH * 0.47f);

                // 4. User name
                using var nf = new Font("Impact", capSh * 0.088f, FontStyle.Bold);
                using var nb = new SolidBrush(capU.Accent);
                var nsz = g.MeasureString(capU.Name, nf);
                g.DrawString(capU.Name, nf, nb, (capSw - nsz.Width) / 2f, capBodyH * 0.59f);

                // 5. Marker recognised
                using var mf = new Font("Consolas", capSh * 0.015f);
                using var mg = new SolidBrush(capU.Glow);
                string mt = $"TUIO marker  #{capUid}  recognised";
                var msz = g.MeasureString(mt, mf);
                g.DrawString(mt, mf, mg, (capSw - msz.Width) / 2f, capBodyH * 0.76f);

                // 6. Accent divider
                int dw = (int)(capSw * 0.40), dx = (capSw - dw) / 2, dy = (int)(capBodyH * 0.855);
                using var db = new SolidBrush(capU.Accent);
                g.FillRectangle(db, dx, dy, dw, 4);
            };

            // Start GIF
            BeginInvoke(new Action(() =>
            {
                if (_screen != root) return;
                _gifPlayer = new GifPlayer(u.GifPath, frame =>
                {
                    _currentGifFrame = frame;
                    if (!canvas.IsDisposed) canvas.Invalidate();
                });
            }));

            if (_menuOverlay != null) { _menuOverlay.Bounds = ClientRectangle; _menuOverlay.BringToFront(); }
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
        //  GAME LAUNCH
        // ═══════════════════════════════════════════════════════════════════════

        private void DoLaunchGame()
        {
            string name = _currentUser.HasValue ? _users[_currentUser.Value].Name : "";
            _useTuioControl = _currentUser.HasValue && _tuioControlUsers.Contains(_currentUser.Value);

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
            else ShowError(errMsg);
        }

        private bool LaunchGame(string characterName, out string errorMsg)
        {
            errorMsg = "Game executable not configured. Set game path in AppConfig.";
            return false;
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