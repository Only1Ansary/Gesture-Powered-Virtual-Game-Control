using System.Drawing.Drawing2D;
using System.Net;
using System.Net.Sockets;
using System.Text;

namespace CircularMenu
{
    public partial class Form1 : Form
    {
        public Form1()
        {
            InitializeComponent();
            this.FormBorderStyle = FormBorderStyle.None;
            this.WindowState = FormWindowState.Maximized;
            this.TopMost = true;
            this.BackColor = Color.FromArgb(7, 7, 15);
            this.DoubleBuffered = true;

            InitWedges();

            tuioListener = new MinimalTuioListener();
            tuioListener.OnMarkerRotated += TuioListener_OnMarkerRotated;
            tuioListener.Start(3333);

            System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();
            timer.Interval = 16; // ~60fps
            timer.Tick += Timer_Tick;
            timer.Start();
        }

        public class MinimalTuioListener
        {
            private UdpClient udpClient;
            private Thread thread;
            private bool running;
            public event Action<int, float> OnMarkerRotated;

            public void Start(int port = 3333)
            {
                udpClient = new UdpClient(port);
                running = true;
                thread = new Thread(Listen);
                thread.IsBackground = true;
                thread.Start();
            }

            public void Stop()
            {
                running = false;
                if (udpClient != null) udpClient.Close();
            }

            private void Listen()
            {
                IPEndPoint ep = new IPEndPoint(IPAddress.Any, 0);
                while (running)
                {
                    try
                    {
                        if (udpClient == null) break;
                        byte[] data = udpClient.Receive(ref ep);
                        ParseOsc(data);
                    }
                    catch { }
                }
            }

            private void ParseOsc(byte[] data)
            {
                int index = 0;
                string address = ReadString(data, ref index);
                if (address == "#bundle")
                {
                    index += 8; // skip time tag
                    while (index < data.Length)
                    {
                        int length = ReadInt(data, ref index);
                        int nextIndex = index + length;
                        if (nextIndex > data.Length) break;
                        ParseMessage(data, ref index);
                        index = nextIndex;
                    }
                }
                else
                {
                    ParseMessage(data, ref index, address);
                }
            }

            private void ParseMessage(byte[] data, ref int index, string address = null)
            {
                if (address == null)
                    address = ReadString(data, ref index);

                if (address == "/tuio/2Dobj")
                {
                    string typeTags = ReadString(data, ref index);
                    if (typeTags.StartsWith(","))
                    {
                        string command = ReadString(data, ref index);
                        if (command == "set")
                        {
                            int sessionId = ReadInt(data, ref index);
                            int classId = ReadInt(data, ref index); // Marker ID
                            float x = ReadFloat(data, ref index);
                            float y = ReadFloat(data, ref index);
                            float a = ReadFloat(data, ref index); // Angle

                            if (OnMarkerRotated != null) OnMarkerRotated(classId, a);
                        }
                    }
                }
            }

            private string ReadString(byte[] data, ref int index)
            {
                int start = index;
                while (index < data.Length && data[index] != 0) index++;
                string s = Encoding.ASCII.GetString(data, start, index - start);
                index++; // skip null
                while (index % 4 != 0) index++; // pad to 4 bytes
                return s;
            }

            private int ReadInt(byte[] data, ref int index)
            {
                if (index + 4 > data.Length) return 0;
                if (BitConverter.IsLittleEndian)
                {
                    byte[] rev = { data[index + 3], data[index + 2], data[index + 1], data[index] };
                    int i = BitConverter.ToInt32(rev, 0);
                    index += 4;
                    return i;
                }
                else
                {
                    int i = BitConverter.ToInt32(data, index);
                    index += 4;
                    return i;
                }
            }

            private float ReadFloat(byte[] data, ref int index)
            {
                if (index + 4 > data.Length) return 0f;
                if (BitConverter.IsLittleEndian)
                {
                    byte[] rev = { data[index + 3], data[index + 2], data[index + 1], data[index] };
                    float f = BitConverter.ToSingle(rev, 0);
                    index += 4;
                    return f;
                }
                else
                {
                    float f = BitConverter.ToSingle(data, index);
                    index += 4;
                    return f;
                }
            }
        }

        public class CircularMenuForm : Form
        {
            private MinimalTuioListener tuioListener;
            private float currentMarkerAngle = -1f; // -1 means no marker
            private string hoveredWedge = "center";

            // Cooldown logic
            private DateTime lastGlobalAction = DateTime.MinValue;
            private DateTime lastVolTime = DateTime.MinValue;
            private string lastTriggeredSector = "";

            private const int MarkerId = 10;
            private const double ActionCooldownS = 2.2;
            private const double VolRepeatS = 0.25;

            private class WedgeSpec
            {
                public string Name;
                public float StartAngle;
                public float SweepAngle;
                public Color DimColor;
                public Color BrightColor;
                public string Text;
                public Font TextFont;
                public PointF TextOffset;
            }

            private List<WedgeSpec> wedges;

            public CircularMenuForm()
            {
                this.FormBorderStyle = FormBorderStyle.None;
                this.WindowState = FormWindowState.Maximized;
                this.TopMost = true;
                this.BackColor = Color.FromArgb(7, 7, 15);
                this.DoubleBuffered = true;

                InitWedges();

                tuioListener = new MinimalTuioListener();
                tuioListener.OnMarkerRotated += TuioListener_OnMarkerRotated;
                tuioListener.Start(3333);

                System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();
                timer.Interval = 16; // ~60fps
                timer.Tick += Timer_Tick;
                timer.Start();
            }

            private void InitWedges()
            {
                wedges = new List<WedgeSpec>();
                Font fontLarge = new Font("Bahnschrift", 20, FontStyle.Bold);
                Font fontSmall = new Font("Bahnschrift", 16, FontStyle.Regular);

                // C# Graphics.FillPie angles: 0 is Right, 90 is Down
                // All 6 wedges are now 60 degrees each.
                // Right (Bottom-Right): 0 to 60
                wedges.Add(new WedgeSpec { Name = "right", StartAngle = 0f, SweepAngle = 60f, DimColor = ColorTranslator.FromHtml("#1a2a4a"), BrightColor = ColorTranslator.FromHtml("#5b8cff"), Text = "MIN OTHERS\n+ GUI", TextFont = fontLarge, TextOffset = new PointF(214, 124) });
                // Down: 60 to 120
                wedges.Add(new WedgeSpec { Name = "down", StartAngle = 60f, SweepAngle = 60f, DimColor = ColorTranslator.FromHtml("#3d2a1a"), BrightColor = ColorTranslator.FromHtml("#ffb020"), Text = "VOL -", TextFont = fontLarge, TextOffset = new PointF(0, 248) });
                // Right-Down (Bottom-Left): 120 to 180
                wedges.Add(new WedgeSpec { Name = "right_down", StartAngle = 120f, SweepAngle = 60f, DimColor = ColorTranslator.FromHtml("#2a3555"), BrightColor = ColorTranslator.FromHtml("#7eb8ff"), Text = "GUI\n(full)\nif game FS", TextFont = fontSmall, TextOffset = new PointF(-214, 124) });
                // Left (Top-Left): 180 to 240
                wedges.Add(new WedgeSpec { Name = "left", StartAngle = 180f, SweepAngle = 60f, DimColor = ColorTranslator.FromHtml("#3d1a2a"), BrightColor = ColorTranslator.FromHtml("#ff5b8c"), Text = "EXIT GAME\n+ GUI", TextFont = fontLarge, TextOffset = new PointF(-214, -124) });
                // Up: 240 to 300
                wedges.Add(new WedgeSpec { Name = "up", StartAngle = 240f, SweepAngle = 60f, DimColor = ColorTranslator.FromHtml("#1a3d2e"), BrightColor = ColorTranslator.FromHtml("#2ee59d"), Text = "VOL +", TextFont = fontLarge, TextOffset = new PointF(0, -248) });
                // Right-Up (Top-Right): 300 to 360
                wedges.Add(new WedgeSpec { Name = "right_up", StartAngle = 300f, SweepAngle = 60f, DimColor = ColorTranslator.FromHtml("#2a3d5a"), BrightColor = ColorTranslator.FromHtml("#6ec0ff"), Text = "GAME ->\nGUI\n(fullscr)", TextFont = fontSmall, TextOffset = new PointF(214, -124) });
            }

            private void TuioListener_OnMarkerRotated(int markerId, float angle)
            {
                if (markerId == MarkerId)
                {
                    currentMarkerAngle = angle;
                }
            }

            private void Timer_Tick(object sender, EventArgs e)
            {
                UpdateLogic();
                Invalidate(); // trigger repaint
            }

            private void UpdateLogic()
            {
                if (currentMarkerAngle < 0) return;

                // angle is 0 (Up) to 2PI. Convert to C# graphics angle (0 = Right, 90 = Down)
                float degrees = (currentMarkerAngle * 180f / (float)Math.PI);
                float graphicsAngle = (degrees - 90f);
                if (graphicsAngle < 0) graphicsAngle += 360f;

                // Determine hovered wedge
                hoveredWedge = "center";
                foreach (var w in wedges)
                {
                    float endAngle = w.StartAngle + w.SweepAngle;
                    bool inside = false;
                    if (endAngle > 360f)
                    {
                        inside = (graphicsAngle >= w.StartAngle && graphicsAngle <= 360f) ||
                                 (graphicsAngle >= 0f && graphicsAngle <= (endAngle - 360f));
                    }
                    else
                    {
                        inside = (graphicsAngle >= w.StartAngle && graphicsAngle <= endAngle);
                    }

                    if (inside)
                    {
                        hoveredWedge = w.Name;
                        break;
                    }
                }

                // Fire Actions
                DateTime now = DateTime.Now;

                // Continuous
                if (hoveredWedge == "up")
                {
                    if ((now - lastVolTime).TotalSeconds >= VolRepeatS)
                    {
                        lastVolTime = now;
                        Console.WriteLine("ACTION: Volume UP");
                    }
                }
                else if (hoveredWedge == "down")
                {
                    if ((now - lastVolTime).TotalSeconds >= VolRepeatS)
                    {
                        lastVolTime = now;
                        Console.WriteLine("ACTION: Volume DOWN");
                    }
                }
                else if (hoveredWedge != "center")
                {
                    // Destructive edge
                    if (hoveredWedge != lastTriggeredSector)
                    {
                        if ((now - lastGlobalAction).TotalSeconds >= ActionCooldownS)
                        {
                            Console.WriteLine(string.Format("ACTION: Triggered {0}", hoveredWedge));
                            lastGlobalAction = now;
                        }
                    }
                }

                lastTriggeredSector = hoveredWedge;
            }

            protected override void OnPaint(PaintEventArgs e)
            {
                base.OnPaint(e);
                Graphics g = e.Graphics;
                g.SmoothingMode = SmoothingMode.AntiAlias;

                int cx = this.Width / 2;
                int cy = this.Height / 2;
                int R = (int)(Math.Min(this.Width, this.Height) * 0.28f);

                // Draw outline
                using (Pen outlinePen = new Pen(ColorTranslator.FromHtml("#2a2a44"), 3))
                {
                    g.DrawEllipse(outlinePen, cx - R - 40, cy - R - 40, (R + 40) * 2, (R + 40) * 2);
                }

                Rectangle rect = new Rectangle(cx - R, cy - R, R * 2, R * 2);

                foreach (var w in wedges)
                {
                    Color fillColor = (hoveredWedge == w.Name) ? w.BrightColor : w.DimColor;
                    using (SolidBrush brush = new SolidBrush(fillColor))
                    {
                        g.FillPie(brush, rect, w.StartAngle, w.SweepAngle);
                    }
                    using (Pen pen = new Pen(ColorTranslator.FromHtml("#444466"), 2))
                    {
                        g.DrawPie(pen, rect, w.StartAngle, w.SweepAngle);
                    }

                    // Text
                    StringFormat sf = new StringFormat();
                    sf.Alignment = StringAlignment.Center;
                    sf.LineAlignment = StringAlignment.Center;
                    using (SolidBrush textBrush = new SolidBrush(ColorTranslator.FromHtml("#cccccc")))
                    {
                        g.DrawString(w.Text, w.TextFont, textBrush, cx + w.TextOffset.X, cy + w.TextOffset.Y, sf);
                    }
                }

                // Draw Rotation Cursor based on TUIO marker angle
                if (currentMarkerAngle >= 0)
                {
                    float degrees = (currentMarkerAngle * 180f / (float)Math.PI);
                    float graphicsAngle = (degrees - 90f);

                    float angleRad = graphicsAngle * (float)Math.PI / 180f;
                    float px = (float)Math.Cos(angleRad) * (R - 20);
                    float py = (float)Math.Sin(angleRad) * (R - 20);

                    using (Pen linePen = new Pen(Color.White, 3))
                    {
                        g.DrawLine(linePen, cx, cy, cx + px, cy + py);
                    }
                    using (SolidBrush dotBrush = new SolidBrush(Color.White))
                    using (Pen dotPen = new Pen(ColorTranslator.FromHtml("#00fff7"), 3))
                    {
                        g.FillEllipse(dotBrush, cx + px - 14, cy + py - 14, 28, 28);
                        g.DrawEllipse(dotPen, cx + px - 14, cy + py - 14, 28, 28);
                    }
                }

                // Draw Instructions
                Font instFont = new Font("Consolas", 12);
                using (SolidBrush instBrush = new SolidBrush(ColorTranslator.FromHtml("#666688")))
                {
                    StringFormat sf = new StringFormat { Alignment = StringAlignment.Center };
                    g.DrawString(string.Format("Rotate TUIO marker {0} to select a wedge. Actions have a {1}s cooldown.", MarkerId, ActionCooldownS), instFont, instBrush, cx, this.Height - 60, sf);

                    // To close the standalone form easily during testing
                    g.DrawString("Press ESC to exit", instFont, instBrush, 100, 50);
                }
            }

            protected override void OnKeyDown(KeyEventArgs e)
            {
                if (e.KeyCode == Keys.Escape)
                {
                    tuioListener.Stop();
                    this.Close();
                }
                base.OnKeyDown(e);
            }

            protected override void OnFormClosing(FormClosingEventArgs e)
            {
                tuioListener.Stop();
                base.OnFormClosing(e);
            }
        }

        private MinimalTuioListener tuioListener;
        private float currentMarkerAngle = -1f; // -1 means no marker
        private string hoveredWedge = "center";

        // Cooldown logic
        private DateTime lastGlobalAction = DateTime.MinValue;
        private DateTime lastVolTime = DateTime.MinValue;
        private string lastTriggeredSector = "";

        private const int MarkerId = 10;
        private const double ActionCooldownS = 2.2;
        private const double VolRepeatS = 0.25;

        private class WedgeSpec
        {
            public string Name;
            public float StartAngle;
            public float SweepAngle;
            public Color DimColor;
            public Color BrightColor;
            public string Text;
            public Font TextFont;
            public PointF TextOffset;
        }

        private List<WedgeSpec> wedges;

        private void InitWedges()
        {
            wedges = new List<WedgeSpec>();
            Font fontLarge = new Font("Bahnschrift", 20, FontStyle.Bold);
            Font fontSmall = new Font("Bahnschrift", 16, FontStyle.Regular);

            // C# Graphics.FillPie angles: 0 is Right, 90 is Down
            // All 6 wedges are now 60 degrees each.
            // Right (Bottom-Right): 0 to 60
            wedges.Add(new WedgeSpec { Name = "right", StartAngle = 0f, SweepAngle = 60f, DimColor = ColorTranslator.FromHtml("#1a2a4a"), BrightColor = ColorTranslator.FromHtml("#5b8cff"), Text = "MIN OTHERS\n+ GUI", TextFont = fontLarge, TextOffset = new PointF(214, 124) });
            // Down: 60 to 120
            wedges.Add(new WedgeSpec { Name = "down", StartAngle = 60f, SweepAngle = 60f, DimColor = ColorTranslator.FromHtml("#3d2a1a"), BrightColor = ColorTranslator.FromHtml("#ffb020"), Text = "VOL -", TextFont = fontLarge, TextOffset = new PointF(0, 248) });
            // Right-Down (Bottom-Left): 120 to 180
            wedges.Add(new WedgeSpec { Name = "right_down", StartAngle = 120f, SweepAngle = 60f, DimColor = ColorTranslator.FromHtml("#2a3555"), BrightColor = ColorTranslator.FromHtml("#7eb8ff"), Text = "GUI\n(full)\nif game FS", TextFont = fontSmall, TextOffset = new PointF(-214, 124) });
            // Left (Top-Left): 180 to 240
            wedges.Add(new WedgeSpec { Name = "left", StartAngle = 180f, SweepAngle = 60f, DimColor = ColorTranslator.FromHtml("#3d1a2a"), BrightColor = ColorTranslator.FromHtml("#ff5b8c"), Text = "EXIT GAME\n+ GUI", TextFont = fontLarge, TextOffset = new PointF(-214, -124) });
            // Up: 240 to 300
            wedges.Add(new WedgeSpec { Name = "up", StartAngle = 240f, SweepAngle = 60f, DimColor = ColorTranslator.FromHtml("#1a3d2e"), BrightColor = ColorTranslator.FromHtml("#2ee59d"), Text = "VOL +", TextFont = fontLarge, TextOffset = new PointF(0, -248) });
            // Right-Up (Top-Right): 300 to 360
            wedges.Add(new WedgeSpec { Name = "right_up", StartAngle = 300f, SweepAngle = 60f, DimColor = ColorTranslator.FromHtml("#2a3d5a"), BrightColor = ColorTranslator.FromHtml("#6ec0ff"), Text = "GAME ->\nGUI\n(fullscr)", TextFont = fontSmall, TextOffset = new PointF(214, -124) });
        }

        private void TuioListener_OnMarkerRotated(int markerId, float angle)
        {
            if (markerId == MarkerId)
            {
                currentMarkerAngle = angle;
            }
        }

        private void Timer_Tick(object sender, EventArgs e)
        {
            UpdateLogic();
            Invalidate(); // trigger repaint
        }

        private void UpdateLogic()
        {
            if (currentMarkerAngle < 0) return;

            // angle is 0 (Up) to 2PI. Convert to C# graphics angle (0 = Right, 90 = Down)
            float degrees = (currentMarkerAngle * 180f / (float)Math.PI);
            float graphicsAngle = (degrees - 90f);
            if (graphicsAngle < 0) graphicsAngle += 360f;

            // Determine hovered wedge
            hoveredWedge = "center";
            foreach (var w in wedges)
            {
                float endAngle = w.StartAngle + w.SweepAngle;
                bool inside = false;
                if (endAngle > 360f)
                {
                    inside = (graphicsAngle >= w.StartAngle && graphicsAngle <= 360f) ||
                             (graphicsAngle >= 0f && graphicsAngle <= (endAngle - 360f));
                }
                else
                {
                    inside = (graphicsAngle >= w.StartAngle && graphicsAngle <= endAngle);
                }

                if (inside)
                {
                    hoveredWedge = w.Name;
                    break;
                }
            }

            // Fire Actions
            DateTime now = DateTime.Now;

            // Continuous
            if (hoveredWedge == "up")
            {
                if ((now - lastVolTime).TotalSeconds >= VolRepeatS)
                {
                    lastVolTime = now;
                    Console.WriteLine("ACTION: Volume UP");
                }
            }
            else if (hoveredWedge == "down")
            {
                if ((now - lastVolTime).TotalSeconds >= VolRepeatS)
                {
                    lastVolTime = now;
                    Console.WriteLine("ACTION: Volume DOWN");
                }
            }
            else if (hoveredWedge != "center")
            {
                // Destructive edge
                if (hoveredWedge != lastTriggeredSector)
                {
                    if ((now - lastGlobalAction).TotalSeconds >= ActionCooldownS)
                    {
                        Console.WriteLine(string.Format("ACTION: Triggered {0}", hoveredWedge));
                        lastGlobalAction = now;
                    }
                }
            }

            lastTriggeredSector = hoveredWedge;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;

            int cx = this.Width / 2;
            int cy = this.Height / 2;
            int R = (int)(Math.Min(this.Width, this.Height) * 0.28f);

            // Draw outline
            using (Pen outlinePen = new Pen(ColorTranslator.FromHtml("#2a2a44"), 3))
            {
                g.DrawEllipse(outlinePen, cx - R - 40, cy - R - 40, (R + 40) * 2, (R + 40) * 2);
            }

            Rectangle rect = new Rectangle(cx - R, cy - R, R * 2, R * 2);

            foreach (var w in wedges)
            {
                Color fillColor = (hoveredWedge == w.Name) ? w.BrightColor : w.DimColor;
                using (SolidBrush brush = new SolidBrush(fillColor))
                {
                    g.FillPie(brush, rect, w.StartAngle, w.SweepAngle);
                }
                using (Pen pen = new Pen(ColorTranslator.FromHtml("#444466"), 2))
                {
                    g.DrawPie(pen, rect, w.StartAngle, w.SweepAngle);
                }

                // Text
                StringFormat sf = new StringFormat();
                sf.Alignment = StringAlignment.Center;
                sf.LineAlignment = StringAlignment.Center;
                using (SolidBrush textBrush = new SolidBrush(ColorTranslator.FromHtml("#cccccc")))
                {
                    g.DrawString(w.Text, w.TextFont, textBrush, cx + w.TextOffset.X, cy + w.TextOffset.Y, sf);
                }
            }

            // Draw Rotation Cursor based on TUIO marker angle
            if (currentMarkerAngle >= 0)
            {
                float degrees = (currentMarkerAngle * 180f / (float)Math.PI);
                float graphicsAngle = (degrees - 90f);

                float angleRad = graphicsAngle * (float)Math.PI / 180f;
                float px = (float)Math.Cos(angleRad) * (R - 20);
                float py = (float)Math.Sin(angleRad) * (R - 20);

                using (Pen linePen = new Pen(Color.White, 3))
                {
                    g.DrawLine(linePen, cx, cy, cx + px, cy + py);
                }
                using (SolidBrush dotBrush = new SolidBrush(Color.White))
                using (Pen dotPen = new Pen(ColorTranslator.FromHtml("#00fff7"), 3))
                {
                    g.FillEllipse(dotBrush, cx + px - 14, cy + py - 14, 28, 28);
                    g.DrawEllipse(dotPen, cx + px - 14, cy + py - 14, 28, 28);
                }
            }

            // Draw Instructions
            Font instFont = new Font("Consolas", 12);
            using (SolidBrush instBrush = new SolidBrush(ColorTranslator.FromHtml("#666688")))
            {
                StringFormat sf = new StringFormat { Alignment = StringAlignment.Center };
                g.DrawString(string.Format("Rotate TUIO marker {0} to select a wedge. Actions have a {1}s cooldown.", MarkerId, ActionCooldownS), instFont, instBrush, cx, this.Height - 60, sf);

                // To close the standalone form easily during testing
                g.DrawString("Press ESC to exit", instFont, instBrush, 100, 50);
            }
        }

        protected override void OnKeyDown(KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Escape)
            {
                tuioListener.Stop();
                this.Close();
            }
            base.OnKeyDown(e);
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            tuioListener.Stop();
            base.OnFormClosing(e);
        }
    }
}
