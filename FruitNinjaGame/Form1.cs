using System.Drawing.Drawing2D;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using NAudio.Wave;

namespace FruitNinjaGame
{
    public partial class Form1 : Form
    {
        System.Windows.Forms.Timer T = new System.Windows.Forms.Timer();
        Bitmap off;
        private readonly object levelLock = new object();
        private readonly object toolLock = new object();
        private readonly GameAudioPlayer audio = new GameAudioPlayer();
        private bool isClosing = false;
        private ToolMode currentTool = ToolMode.Sword;
        private bool toolActive = false;
        private string yoloStatus = "none";
        private string yoloCandidate = "none";
        private float yoloConfidence = 0f;
        private float yoloCursorX = -1f;
        private float yoloCursorY = -1f;
        private int yoloPixelX = -1;
        private int yoloPixelY = -1;
        private int yoloUpdateCount = 0;

        private enum ToolMode
        {
            Sword,
            Stick
        }

        // ── Per-user high score ───────────────────────────────────────────────
        private int _userId = -1;          // -1 = no user / guest
        private int HighScore = 0;
        private Fruit HighScoreIcon = new Fruit();   // reuses the score.png asset
        private Score HighScoreNum = new Score();

        public Form1() : this(-1) { }

        public Form1(int userId)
        {
            _userId = userId;
            // Load persisted high score for this user (0 if guest / not found)
            HighScore = userId >= 0 ? UserStore.LoadHighScore(userId) : 0;

            InitializeComponent();
            this.FormBorderStyle = FormBorderStyle.None;
            Cursor.Hide();
            this.WindowState = FormWindowState.Maximized;
            this.Load += Form1_Load;
            this.Paint += Form1_Paint;
            T.Tick += T_Tick;
            T.Start();
            this.KeyDown += Form1_KeyDown;
            this.MouseMove += Form1_MouseMove;
            this.FormClosing += (_, _) =>
            {
                isClosing = true;
                audio.StopMusic();
            };
            this.FormClosed += (_, _) =>
            {
                isClosing = true;
                audio.Dispose();
            };
        }

        private void Form1_MouseMove(object? sender, MouseEventArgs e) => ProcessPointerMove(e.X, e.Y);

        /// <summary>TUIO normalized [0,1] × [0,1] → same logic as the physical mouse (menu + blade).</summary>
        public void FeedTuioPointer(float tuioX, float tuioY)
        {
            if (IsDisposed) return;
            if (InvokeRequired)
            {
                try { BeginInvoke(new Action(() => FeedTuioPointer(tuioX, tuioY))); } catch { }
                return;
            }

            int w = Math.Max(1, ClientSize.Width);
            int h = Math.Max(1, ClientSize.Height);
            tuioX = Math.Clamp(tuioX, 0f, 1f);
            tuioY = Math.Clamp(tuioY, 0f, 1f);
            int cx = (int)(tuioX * (w - 1));
            int cy = (int)(tuioY * (h - 1));
            ProcessPointerMove(cx, cy);
        }

        private void ProcessPointerMove(int px, int py)
        {
            if (isOver)
            {
                if (RetryIconState == 0)
                {
                    if (px >= RetryIcon.X &&
                        px <= RetryIcon.X + RetryIcon.img[0].Width + 10 &&
                        py >= RetryIcon.Y &&
                        py <= RetryIcon.Y + RetryIcon.img[0].Height + 10)
                    {
                        RetryIconState = 1;
                    }
                }

                if (ExitIconState == 0)
                {
                    if (px >= GameOverExitIcon.X &&
                        px <= GameOverExitIcon.X + 130 &&
                        py >= GameOverExitIcon.Y &&
                        py <= GameOverExitIcon.Y + 130)
                    {
                        ExitIconState = 1;
                        create_explosion(GameOverExitIcon.X, GameOverExitIcon.Y);
                        GameOverExitIcon = null;
                        animate_exp();
                        T.Stop();
                        this.Close();
                    }
                }

            }

            if (isMenu)
            {
                if (px >= StartIcon.X && px <= StartIcon.X + StartIcon.img[0].Width + 10
                && py >= StartIcon.Y && py <= StartIcon.Y + StartIcon.img[0].Height + 10)
                {
                    StartIconState = 1;
                }

                if (ExitIconState == 0)
                {
                    if (px >= ExitIcon.X && px <= ExitIcon.X + 130
                        && py >= ExitIcon.Y && py <= ExitIcon.Y + 130)
                    {
                        ExitIconState = 1;
                        create_explosion(ExitIcon.X, ExitIcon.Y);
                        ExitIcon = null;
                        animate_exp();
                        T.Stop();
                        this.Close();
                    }
                }
            }

            if (isGame && !isOver)
            {
                Rectangle swordRect = new Rectangle(
                    px - 60,
                    py - 60,
                    120,
                    120
                );

                for (int i = 0; i < Fruits.Count; i++)
                {
                    Rectangle fruitRect = new Rectangle(
                        Fruits[i].X,
                        Fruits[i].Y,
                        Fruits[i].img[0].Width,
                        Fruits[i].img[0].Height
                    );

                    bool hit = swordRect.IntersectsWith(fruitRect);

                    if (prevX != -1)
                    {
                        Rectangle swipeRect = new Rectangle(
                            Math.Min(prevX, px),
                            Math.Min(prevY, py),
                            Math.Abs(prevX - px),
                            Math.Abs(prevY - py)
                        );

                        hit = hit || swipeRect.IntersectsWith(fruitRect);
                    }

                    if (hit && Fruits[i].isCut == 0)
                    {
                        Fruits[i].isCut = 1;
                        ScoreCount++;
                        if (IsToolActive())
                            audio.PlayFruitHit(GetCurrentTool() == ToolMode.Stick);
                    }
                }

                for (int i = 0; i < Bombs.Count; i++)
                {
                    Rectangle bombRect = new Rectangle(
                        Bombs[i].X,
                        Bombs[i].Y,
                        130,
                        130
                    );

                    bool hit = swordRect.IntersectsWith(bombRect);

                    if (prevX != -1)
                    {
                        Rectangle swipeRect = new Rectangle(
                            Math.Min(prevX, px),
                            Math.Min(prevY, py),
                            Math.Abs(prevX - px),
                            Math.Abs(prevY - py)
                        );

                        hit = hit || swipeRect.IntersectsWith(bombRect);
                    }

                    if (hit)
                    {
                        if (IsToolActive())
                            audio.PlayExplosion();
                        create_explosion(Bombs[i].X, Bombs[i].Y);
                        animate_exp();
                        Bombs.RemoveAt(i);
                        LivesCount--;
                        if (LivesCount == 0)
                        {
                            isOver = true;
                            GameOver = new Bitmap(AppConfig.GetAssetPath("GameOver.png"));
                            audio.StopMusic();
                            Fruits.Clear();
                            Bombs.Clear();
                            // ── Persist high score on game over ───────────────
                            if (_userId >= 0)
                                HighScore = UserStore.SaveHighScore(_userId, ScoreCount);
                            else if (ScoreCount > HighScore)
                                HighScore = ScoreCount;
                            DrawGameOver();
                        }
                    }
                }
            }

            Blade.X = px;
            Blade.Y = py;
            prevX = px;
            prevY = py;
        }

        public class Score
        {
            public List<Bitmap> First = new List<Bitmap>();
            public List<Bitmap> Second = new List<Bitmap>();
            public List<Bitmap> Third = new List<Bitmap>();
            public List<Bitmap> Fourth = new List<Bitmap>();
        }

        public class Fruit
        {
            public int X = 0;
            public int Y = 0;
            public float Vx;
            public float Vy;
            public int isCut = 0;
            public List<Bitmap> img = new List<Bitmap>();
        }

        public class Bomb
        {
            public int X;
            public int Y;
            public int Frame;
            public List<Bitmap> img = new List<Bitmap>();
        }


        int ScoreCount = 0;
        int StartIconState = 0;
        int ExitIconState = 0;
        int RetryIconState = 0;
        int LivesCount = 3;
        int prevX = -1;
        int prevY = -1;

        bool isMenu = true;
        bool isGame = false;
        bool isOver = false;

        float startAngle = 0;
        float exitAngle = 0;
        float retryangle = 0;

        Bitmap back;
        Bitmap GameOver;
        Bitmap GameName;
        Bitmap StartRing;
        Bitmap ExitRing;
        Bitmap RetryRing;

        Fruit StartIcon = new Fruit();
        Fruit ExitIcon = new Fruit();
        Fruit Lives = new Fruit();
        Fruit ScoreIcon = new Fruit();
        Fruit Blade = new Fruit();

        List<Bitmap> FruitImg = new List<Bitmap>();
        List<Fruit> Fruits = new List<Fruit>();
        List<Fruit> Bombs = new List<Fruit>();
        List<Bomb> Exp = new List<Bomb>();

        Score ScoreNum = new Score();

        void create_explosion(int X, int Y)
        {
            Bomb pnn = new Bomb();
            pnn.X = X;
            pnn.Y = Y;
            pnn.Frame = 0;
            pnn.img = new List<Bitmap>();
            pnn.img.Add(new Bitmap(AppConfig.GetAssetPath("ex1.png")));
            pnn.img.Add(new Bitmap(AppConfig.GetAssetPath("ex2.png")));
            pnn.img.Add(new Bitmap(AppConfig.GetAssetPath("ex3.png")));
            pnn.img.Add(new Bitmap(AppConfig.GetAssetPath("ex4.png")));
            pnn.img.Add(new Bitmap(AppConfig.GetAssetPath("ex5.png")));
            Exp.Add(pnn);
        }
        void animate_exp()
        {
            for (int i = 0; i < Exp.Count; i++)
            {
                for (int a = 0; a < 5; a++)
                {
                    Exp[i].Frame++;
                    if (Exp[i].Frame > 4)
                    {
                        Exp.Remove(Exp[i]);
                    }
                    DrawDubb(this.CreateGraphics());
                }
            }
        }


        public void SetDifficultyLevel(int level)
        {
            lock (levelLock)
            {
                Level = level;
            }
            Console.WriteLine($"[FruitNinja] Difficulty Level set to {level} ({GetDifficultyMode()})");
        }

        public void SetToolState(string toolState)
        {
            if (isClosing || IsDisposed) return;
            if (InvokeRequired)
            {
                try { BeginInvoke(new Action(() => SetToolState(toolState))); } catch { }
                return;
            }

            string[] parts = (toolState ?? "").Trim().Split('|');
            string normalized = parts.Length > 0 ? parts[0].Trim().ToLowerInvariant() : "none";
            float confidence = 0f;
            if (parts.Length > 1)
                float.TryParse(parts[1], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out confidence);
            string candidate = parts.Length > 2 ? parts[2].Trim().ToLowerInvariant() : normalized;
            float normX = 0.5f;
            float normY = 0.5f;
            bool hasPointer =
                parts.Length > 4 &&
                float.TryParse(parts[3], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out normX) &&
                float.TryParse(parts[4], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out normY);

            bool nextToolActive = normalized == "sword" || normalized == "stick";
            ToolMode nextTool = normalized == "stick" ? ToolMode.Stick : ToolMode.Sword;
            lock (toolLock)
            {
                currentTool = nextTool;
                toolActive = nextToolActive;
                yoloStatus = normalized;
                yoloCandidate = string.IsNullOrWhiteSpace(candidate) ? "none" : candidate;
                yoloConfidence = confidence;
            }

            if (hasPointer)
            {
                FeedYoloPointer(normX, normY);
            }

            if (!nextToolActive || isOver)
            {
                audio.PauseMusic();
            }
            else if (isGame)
            {
                audio.PlayGameplayMusic();
            }
            else if (isMenu)
            {
                audio.PlayStartMusic();
            }
        }

        private void FeedYoloPointer(float normalizedX, float normalizedY)
        {
            normalizedX = Math.Clamp(normalizedX, 0f, 1f);
            normalizedY = Math.Clamp(normalizedY, 0f, 1f);

            if (yoloCursorX < 0f || yoloCursorY < 0f)
            {
                yoloCursorX = normalizedX;
                yoloCursorY = normalizedY;
            }
            else
            {
                const float alpha = 0.75f;
                yoloCursorX = yoloCursorX + (normalizedX - yoloCursorX) * alpha;
                yoloCursorY = yoloCursorY + (normalizedY - yoloCursorY) * alpha;
            }

            int px = (int)(yoloCursorX * Math.Max(1, ClientSize.Width - 1));
            int py = (int)(yoloCursorY * Math.Max(1, ClientSize.Height - 1));
            lock (toolLock)
            {
                yoloPixelX = px;
                yoloPixelY = py;
                yoloUpdateCount++;
            }
            ProcessPointerMove(px, py);
        }

        private ToolMode GetCurrentTool()
        {
            lock (toolLock)
            {
                return currentTool;
            }
        }

        private int GetCurrentToolImageIndex()
        {
            return GetCurrentTool() == ToolMode.Stick && Blade.img.Count > 1 ? 1 : 0;
        }

        private bool IsToolActive()
        {
            lock (toolLock)
            {
                return toolActive;
            }
        }

        private string GetYoloHudText()
        {
            lock (toolLock)
            {
                return $"YOLO: {yoloStatus}  candidate: {yoloCandidate}  confidence: {yoloConfidence:0.00}  xy: {yoloPixelX},{yoloPixelY}  updates: {yoloUpdateCount}";
            }
        }


        void DrawScore()
        {
            Bitmap num = new Bitmap(AppConfig.GetAssetPath("zero.png"));
            ScoreNum.First.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("one.png"));
            ScoreNum.First.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("two.png"));
            ScoreNum.First.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("three.png"));
            ScoreNum.First.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("four.png"));
            ScoreNum.First.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("five.png"));
            ScoreNum.First.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("six.png"));
            ScoreNum.First.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("seven.png"));
            ScoreNum.First.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("eight.png"));
            ScoreNum.First.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("nine.png"));
            ScoreNum.First.Add(num);

            num = new Bitmap(AppConfig.GetAssetPath("zero.png"));
            ScoreNum.Second.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("one.png"));
            ScoreNum.Second.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("two.png"));
            ScoreNum.Second.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("three.png"));
            ScoreNum.Second.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("four.png"));
            ScoreNum.Second.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("five.png"));
            ScoreNum.Second.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("six.png"));
            ScoreNum.Second.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("seven.png"));
            ScoreNum.Second.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("eight.png"));
            ScoreNum.Second.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("nine.png"));
            ScoreNum.Second.Add(num);

            num = new Bitmap(AppConfig.GetAssetPath("zero.png"));
            ScoreNum.Third.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("one.png"));
            ScoreNum.Third.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("two.png"));
            ScoreNum.Third.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("three.png"));
            ScoreNum.Third.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("four.png"));
            ScoreNum.Third.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("five.png"));
            ScoreNum.Third.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("six.png"));
            ScoreNum.Third.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("seven.png"));
            ScoreNum.Third.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("eight.png"));
            ScoreNum.Third.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("nine.png"));
            ScoreNum.Third.Add(num);

            num = new Bitmap(AppConfig.GetAssetPath("zero.png"));
            ScoreNum.Fourth.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("one.png"));
            ScoreNum.Fourth.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("two.png"));
            ScoreNum.Fourth.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("three.png"));
            ScoreNum.Fourth.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("four.png"));
            ScoreNum.Fourth.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("five.png"));
            ScoreNum.Fourth.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("six.png"));
            ScoreNum.Fourth.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("seven.png"));
            ScoreNum.Fourth.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("eight.png"));
            ScoreNum.Fourth.Add(num);
            num = new Bitmap(AppConfig.GetAssetPath("nine.png"));
            ScoreNum.Fourth.Add(num);
        }

        void DrawFruits()
        {
            Bitmap img = new Bitmap(AppConfig.GetAssetPath("full_water.png"));
            FruitImg.Add(img);

            img = new Bitmap(AppConfig.GetAssetPath("half_water.png"));
            FruitImg.Add(img);

            img = new Bitmap(AppConfig.GetAssetPath("full_banana.png"));
            FruitImg.Add(img);

            img = new Bitmap(AppConfig.GetAssetPath("half_banana.png"));
            FruitImg.Add(img);

            img = new Bitmap(AppConfig.GetAssetPath("full_green_apple.png"));
            FruitImg.Add(img);

            img = new Bitmap(AppConfig.GetAssetPath("half_green_apple.png"));
            FruitImg.Add(img);

            img = new Bitmap(AppConfig.GetAssetPath("full_red_apple.png"));
            FruitImg.Add(img);

            img = new Bitmap(AppConfig.GetAssetPath("half_red_apple.png"));
            FruitImg.Add(img);

            img = new Bitmap(AppConfig.GetAssetPath("full_lemon.png"));
            FruitImg.Add(img);

            img = new Bitmap(AppConfig.GetAssetPath("half_lemon.png"));
            FruitImg.Add(img);

            img = new Bitmap(AppConfig.GetAssetPath("full_orange.png"));
            FruitImg.Add(img);

            img = new Bitmap(AppConfig.GetAssetPath("half_orange.png"));
            FruitImg.Add(img);

            img = new Bitmap(AppConfig.GetAssetPath("full_coco.png"));
            FruitImg.Add(img);

            img = new Bitmap(AppConfig.GetAssetPath("half_coco.png"));
            FruitImg.Add(img);

            img = new Bitmap(AppConfig.GetAssetPath("full_pear.png"));
            FruitImg.Add(img);

            img = new Bitmap(AppConfig.GetAssetPath("half_pear.png"));
            FruitImg.Add(img);

        }

        void CreateFruit(int Type, int X)
        {
            Fruit pnn = new Fruit();
            pnn.X = X;
            pnn.Y = this.ClientSize.Height + 100;
            pnn.Vy = -R.Next(50, 60);
            pnn.Vx = R.Next(-8, 9);
            pnn.img.Add(FruitImg[Type]);
            pnn.img.Add(FruitImg[Type + 1]);

            Fruits.Add(pnn);
        }

        void CreateBomb(int X)
        {
            Fruit pnn = new Fruit();
            pnn.X = X;
            pnn.Y = this.ClientSize.Height + 100;
            pnn.Vy = -R.Next(50, 60);
            pnn.Vx = R.Next(-8, 9);
            Bitmap img = new Bitmap(AppConfig.GetAssetPath("bomb.png"));
            pnn.img.Add(img);

            Bombs.Add(pnn);
        }

        void StartGame()
        {
            isGame = true;
            DrawFruits();
            Fruit pnn = new Fruit();
            Bitmap img = new Bitmap(AppConfig.GetAssetPath("no_life.png"));
            pnn.img.Add(img);
            img = new Bitmap(AppConfig.GetAssetPath("life2.png"));
            pnn.img.Add(img);
            img = new Bitmap(AppConfig.GetAssetPath("life1.png"));
            pnn.img.Add(img);
            img = new Bitmap(AppConfig.GetAssetPath("full_life.png"));
            pnn.img.Add(img);
            pnn.X = this.ClientSize.Width - 250;
            pnn.Y = 10;
            Lives = pnn;

            pnn = new Fruit();
            pnn.X = 10;
            pnn.Y = 10;
            img = new Bitmap(AppConfig.GetAssetPath("score.png"));
            pnn.img.Add(img);
            ScoreIcon = pnn;

            // ── High-score icon (same asset, positioned below the live score) ──
            Fruit hsPnn = new Fruit();
            hsPnn.X = 10;
            hsPnn.Y = 80;   // 70 px below ScoreIcon (icon h=70)
            Bitmap hsImg = new Bitmap(AppConfig.GetAssetPath("score.png"));
            hsPnn.img.Add(hsImg);
            HighScoreIcon = hsPnn;

            DrawScore();
            DrawHighScoreNum();
        }

        /// <summary>Loads digit bitmaps into <see cref="HighScoreNum"/> (same assets as the live score).</summary>
        void DrawHighScoreNum()
        {
            string[] names = { "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine" };
            foreach (string n in names) HighScoreNum.First.Add(new Bitmap(AppConfig.GetAssetPath($"{n}.png")));
            foreach (string n in names) HighScoreNum.Second.Add(new Bitmap(AppConfig.GetAssetPath($"{n}.png")));
            foreach (string n in names) HighScoreNum.Third.Add(new Bitmap(AppConfig.GetAssetPath($"{n}.png")));
            foreach (string n in names) HighScoreNum.Fourth.Add(new Bitmap(AppConfig.GetAssetPath($"{n}.png")));
        }

        /// <summary>Draw a 1-4 digit number using the number-asset bitmaps at the requested position.</summary>
        void DrawNumericValue(Graphics g, Score digits, int value, int x, int y, int w, int h)
        {
            int ones = value % 10;
            int tens = (value / 10) % 10;
            int hundreds = (value / 100) % 10;
            int thousands = (value / 1000) % 10;

            if (value < 10)
            {
                g.DrawImage(digits.First[ones], x, y, w, h);
            }
            else if (value < 100)
            {
                g.DrawImage(digits.First[tens], x, y, w, h);
                g.DrawImage(digits.Second[ones], x + 40, y, w, h);
            }
            else if (value < 1000)
            {
                g.DrawImage(digits.First[hundreds], x, y, w, h);
                g.DrawImage(digits.Second[tens], x + 40, y, w, h);
                g.DrawImage(digits.Third[ones], x + 80, y, w, h);
            }
            else
            {
                g.DrawImage(digits.First[thousands], x, y, w, h);
                g.DrawImage(digits.Second[hundreds], x + 40, y, w, h);
                g.DrawImage(digits.Third[tens], x + 80, y, w, h);
                g.DrawImage(digits.Fourth[ones], x + 120, y, w, h);
            }
        }

        void StartMenu()
        {
            back = new Bitmap(AppConfig.GetAssetPath("WoodBG.jpg"));
            GameName = new Bitmap(AppConfig.GetAssetPath("Name.png"));
            StartRing = new Bitmap(AppConfig.GetAssetPath("start_ring.png"));
            ExitRing = new Bitmap(AppConfig.GetAssetPath("exit_ring.png"));


            Fruit pnn = new Fruit();
            pnn.X = this.ClientSize.Width / 2 - 405;
            pnn.Y = this.ClientSize.Height / 2 - 20;
            Bitmap StartIcon = new Bitmap(AppConfig.GetAssetPath("full_water.png"));
            pnn.img.Add(StartIcon);
            StartIcon = new Bitmap(AppConfig.GetAssetPath("half_water.png"));
            pnn.img.Add(StartIcon);
            this.StartIcon = pnn;

            Bitmap ExiIcon = new Bitmap(AppConfig.GetAssetPath("bomb.png"));

            Fruit pn = new Fruit();
            pn.X = this.ClientSize.Width / 2 + 290;
            pn.Y = this.ClientSize.Height / 2 - 20;
            pn.img.Add(ExiIcon);
            ExitIcon = pn;
        }


        Fruit RetryIcon = new Fruit();
        Fruit GameOverExitIcon = new Fruit();

        void DrawGameOver()
        {
            Fruit pnn = new Fruit();
            pnn.X = this.ClientSize.Width / 2 - 400;
            pnn.Y = this.ClientSize.Height / 2 + 100;
            pnn.isCut = 0;

            Bitmap img = new Bitmap(AppConfig.GetAssetPath("full_coco.png"));
            pnn.img.Add(img);

            img = new Bitmap(AppConfig.GetAssetPath("half_coco.png"));
            pnn.img.Add(img);

            RetryIcon = pnn;

            RetryRing = new Bitmap(AppConfig.GetAssetPath("retry_ring.png"));

            Fruit exit = new Fruit();
            exit.X = this.ClientSize.Width / 2 + 300;
            exit.Y = this.ClientSize.Height / 2 + 80;

            Bitmap exitImg = new Bitmap(AppConfig.GetAssetPath("bomb.png"));
            exit.img.Add(exitImg);

            GameOverExitIcon = exit;
        }

        void DrawRotatedImage(Graphics g, Image img, float x, float y, float w, float h, float angle)
        {
            var state = g.Save();

            g.TranslateTransform(x + w / 2, y + h / 2);

            g.RotateTransform(angle);

            g.DrawImage(img, -w / 2, -h / 2, w, h);

            g.Restore(state);
        }

        void DrawScene(Graphics g)
        {
            g.Clear(Color.White);

            g.DrawImage(back, 0, 0, this.ClientSize.Width, this.ClientSize.Height);
            if (isOver)
            {
                g.DrawImage(GameOver, 0, -100, this.ClientSize.Width, this.ClientSize.Height);

                { // Save current state
                    var state = g.Save();

                    // Move origin to rotation center (example: center of rectangle)
                    g.TranslateTransform(this.ClientSize.Width / 2, 90);

                    // Rotate (degrees)
                    g.RotateTransform(-5); // rotate 30 degrees

                    // Draw rectangle centered around the new origin
                    int w = this.ClientSize.Width;
                    int h = 180;

                    using (SolidBrush brush = new SolidBrush(Color.FromArgb(120, 0, 0, 0)))
                    {
                        g.FillRectangle(brush, -w / 2 - 10, -h / 2 - 60, w, h);
                    }


                    // Restore original state
                    g.Restore(state);
                }


                DrawRotatedImage(g, RetryRing,
                    this.ClientSize.Width / 2 - 500,
                    this.ClientSize.Height / 2,
                    300, 300,
                    retryangle);

                if (RetryIconState == 0)
                {
                    DrawRotatedImage(g,
                        RetryIcon.img[RetryIconState],
                        RetryIcon.X,
                        RetryIcon.Y,
                        RetryIcon.img[0].Width + 10, RetryIcon.img[0].Height + 10,
                        exitAngle);
                }
                else
                {
                    g.DrawImage(
                        RetryIcon.img[RetryIconState],
                        RetryIcon.X - 20,
                        RetryIcon.Y - 10);
                }

                DrawRotatedImage(g, ExitRing,
                    this.ClientSize.Width / 2 + 200,
                    this.ClientSize.Height / 2,
                    300, 300,
                    exitAngle);

                if (ExitIconState == 0)
                {
                    DrawRotatedImage(g, GameOverExitIcon.img[0],
                    GameOverExitIcon.X, GameOverExitIcon.Y,
                    130, 130,
                    retryangle);
                }
            }

            if (isMenu)
            {
                { // Save current state
                    var state = g.Save();

                    // Move origin to rotation center (example: center of rectangle)
                    g.TranslateTransform(this.ClientSize.Width / 2, 90);

                    // Rotate (degrees)
                    g.RotateTransform(-5); // rotate 30 degrees

                    // Draw rectangle centered around the new origin
                    int w = this.ClientSize.Width;
                    int h = 180;

                    using (SolidBrush brush = new SolidBrush(Color.FromArgb(120, 0, 0, 0)))
                    {
                        g.FillRectangle(brush, -w / 2 - 10, -h / 2 - 60, w, h);
                    }


                    // Restore original state
                    g.Restore(state);
                }
                g.DrawImage(GameName, 0, 0, GameName.Width + 60, GameName.Height + 50);

                DrawRotatedImage(g, StartRing,
                    this.ClientSize.Width / 2 - 500,
                    this.ClientSize.Height / 2 - 100,
                    300, 300,
                    startAngle);


                if (StartIconState == 0)
                {
                    DrawRotatedImage(g, StartIcon.img[StartIconState],
                    StartIcon.X, StartIcon.Y,
                    StartIcon.img[StartIconState].Width + 10, StartIcon.img[StartIconState].Height + 10,
                    exitAngle);
                }
                else
                {
                    g.DrawImage(StartIcon.img[StartIconState], StartIcon.X - 20, StartIcon.Y - 10);
                }


                DrawRotatedImage(g, ExitRing,
                    this.ClientSize.Width / 2 + 200,
                    this.ClientSize.Height / 2 - 100,
                    300, 300,
                    exitAngle);

                if (ExitIconState == 0)
                {
                    DrawRotatedImage(g, ExitIcon.img[0],
                   ExitIcon.X, ExitIcon.Y,
                    130, 130,
                    startAngle);
                }


            }
            else
            {
                g.DrawImage(Lives.img[LivesCount], Lives.X, Lives.Y, 220, 100);
                g.DrawImage(ScoreIcon.img[0], ScoreIcon.X, ScoreIcon.Y, 70, 70);

                int x = ScoreIcon.X + 80;
                int y = 20;
                int w = 40;
                int h = 50;

                // ── Current score (existing behaviour, now via shared helper) ──
                DrawNumericValue(g, ScoreNum, ScoreCount, x, y, w, h);

                // ── High score row (below the current score) ──────────────────
                g.DrawImage(HighScoreIcon.img[0], HighScoreIcon.X, HighScoreIcon.Y, 70, 70);

                int hsX = HighScoreIcon.X + 80;
                int hsY = HighScoreIcon.Y + 10;
                DrawNumericValue(g, HighScoreNum, HighScore, hsX, hsY, w, h);
            }

            if (isGame)
            {
                for (int i = 0; i < Fruits.Count; i++)
                {
                    g.DrawImage(Fruits[i].img[Fruits[i].isCut], Fruits[i].X, Fruits[i].Y);
                }

                for (int i = 0; i < Bombs.Count; i++)
                {
                    g.DrawImage(Bombs[i].img[0], Bombs[i].X, Bombs[i].Y, 130, 130);
                }
            }

            for (int i = 0; i < Exp.Count; i++)
            {
                g.DrawImage(Exp[i].img[Exp[i].Frame], Exp[i].X, Exp[i].Y);
            }

            // ── Difficulty mode label (top centre) ─────────────────────────────────
            if (isGame && !isOver)
            {
                string mode = GetDifficultyMode();
                string displayText = $"Mode: {mode}";
                using (Font modeFont = new Font("Segoe UI", 18, FontStyle.Bold))
                {
                    SizeF textSize = g.MeasureString(displayText, modeFont);
                    int boxPadding = 20;
                    int boxWidth = (int)textSize.Width + boxPadding * 2;
                    int boxHeight = (int)textSize.Height + 12;
                    int x = (this.ClientSize.Width - boxWidth) / 2;
                    int y = 20;  // distance from top

                    // Draw semi‑transparent background
                    using (SolidBrush bgBrush = new SolidBrush(Color.FromArgb(180, 0, 0, 0)))
                    using (Pen borderPen = new Pen(Color.FromArgb(255, 255, 200, 100), 2))
                    {
                        FillRoundedRectangle(g, bgBrush, x, y, boxWidth, boxHeight, 15);
                        //DrawRoundedRectangle(g,borderPen, x, y, boxWidth, boxHeight, 15);
                    }

                    // Choose text colour based on mode
                    Color textColor = mode switch
                    {
                        "Easy" => Color.LightGreen,
                        "Hard" => Color.OrangeRed,
                        _ => Color.LightBlue
                    };
                    using (SolidBrush textBrush = new SolidBrush(textColor))
                    {
                        float textX = x + (boxWidth - textSize.Width) / 2;
                        float textY = y + (boxHeight - textSize.Height) / 2;
                        g.DrawString(displayText, modeFont, textBrush, textX, textY);
                    }
                }
            }

            //DrawYoloHud(g);
            DrawYoloPointerMarker(g);

            int toolImageIndex = GetCurrentToolImageIndex();
            g.DrawImage(Blade.img[toolImageIndex], Blade.X, Blade.Y, Blade.img[toolImageIndex].Width - 150, Blade.img[toolImageIndex].Height - 150);
        }

        private void DrawYoloHud(Graphics g)
        {
            string text = GetYoloHudText();
            using (Font hudFont = new Font("Consolas", 15, FontStyle.Bold))
            {
                SizeF textSize = g.MeasureString(text, hudFont);
                int x = 20;
                int y = 95;
                int padding = 14;

                using (SolidBrush bgBrush = new SolidBrush(Color.FromArgb(185, 0, 0, 0)))
                using (SolidBrush textBrush = new SolidBrush(IsToolActive() ? Color.LimeGreen : Color.OrangeRed))
                {
                    FillRoundedRectangle(g, bgBrush, x, y, (int)textSize.Width + padding * 2, (int)textSize.Height + padding, 12);
                    g.DrawString(text, hudFont, textBrush, x + padding, y + padding / 2);
                }
            }
        }

        private void DrawYoloPointerMarker(Graphics g)
        {
            int px;
            int py;
            bool active;
            lock (toolLock)
            {
                px = yoloPixelX;
                py = yoloPixelY;
                active = toolActive;
            }

            if (px < 0 || py < 0)
                return;

            Color markerColor = active ? Color.Cyan : Color.Gray;
            using (Pen markerPen = new Pen(markerColor, 4))
            using (SolidBrush markerBrush = new SolidBrush(Color.FromArgb(120, markerColor)))
            {
                g.FillEllipse(markerBrush, px - 14, py - 14, 28, 28);
                g.DrawEllipse(markerPen, px - 18, py - 18, 36, 36);
                g.DrawLine(markerPen, px - 28, py, px + 28, py);
                g.DrawLine(markerPen, px, py - 28, px, py + 28);
            }
        }


        private void FillRoundedRectangle(Graphics g, Brush brush, int x, int y, int w, int h, int radius)
        {
            using (GraphicsPath path = new GraphicsPath())
            {
                path.AddArc(x, y, radius * 2, radius * 2, 180, 90);
                path.AddArc(x + w - radius * 2, y, radius * 2, radius * 2, 270, 90);
                path.AddArc(x + w - radius * 2, y + h - radius * 2, radius * 2, radius * 2, 0, 90);
                path.AddArc(x, y + h - radius * 2, radius * 2, radius * 2, 90, 90);
                path.CloseFigure();
                g.FillPath(brush, path);
                g.DrawPath(Pens.Transparent, path); // or a Pen if you want border
            }
        }

        void DrawDubb(Graphics g)
        {
            Graphics g2 = Graphics.FromImage(off);

            DrawScene(g2);

            g.DrawImage(off, 0, 0);
        }

        private void Form1_Paint(object? sender, PaintEventArgs e)
        {
            DrawDubb(e.Graphics);
        }

        private string GetDifficultyMode()
        {
            // Level <= 10  → hard (happy)
            // Level >= 200 → easy (angry/sad)
            // else         → normal
            if (Level <= 10) return "Hard";
            if (Level >= 200) return "Easy";
            return "Normal";
        }

        private void Form1_Load(object? sender, EventArgs e)
        {
            off = new Bitmap(this.ClientSize.Width, this.ClientSize.Height);
            StartMenu();
            Bitmap img = new Bitmap(AppConfig.GetAssetPath("blade.png"));
            Blade.img.Add(img);
            string stickPath = AppConfig.GetAssetPath("stick.png");
            Blade.img.Add(File.Exists(stickPath) ? new Bitmap(stickPath) : img);
        }

        private void Form1_KeyDown(object? sender, KeyEventArgs e)
        {
            switch (e.KeyCode)
            {
                case Keys.Escape:
                    T.Stop();
                    this.Close();
                    break;
            }
        }

        int speed = 5;
        int ct = 0;
        int Level = 100;

        Random R = new Random();


        private void T_Tick(object? sender, EventArgs e)
        {
            if (isOver)
            {
                retryangle += 5;
                exitAngle -= 5;

                if (RetryIconState == 1)
                {
                    RetryIcon.Y += 50;
                }

                if (RetryIcon.Y > this.ClientSize.Height)
                {
                    // Clear all gameplay objects
                    Fruits.Clear();
                    Bombs.Clear();
                    Exp.Clear();

                    // Reset gameplay values
                    ScoreCount = 0;
                    LivesCount = 3;

                    ct = 0;
                    prevX = -1;
                    prevY = -1;

                    // Reset states
                    RetryIconState = 0;
                    ExitIconState = 0;

                    isOver = false;
                    isGame = true;
                    isMenu = false;

                    // Reset retry animation
                    retryangle = 0;
                    exitAngle = 0;

                    // Reset YOLO pointer smoothing
                    yoloCursorX = -1f;
                    yoloCursorY = -1f;
                    yoloPixelX = -1;
                    yoloPixelY = -1;
                    yoloUpdateCount = 0;

                    // Reset blade position
                    Blade.X = this.ClientSize.Width / 2;
                    Blade.Y = this.ClientSize.Height / 2;

                    // Reset difficulty
                    lock (levelLock)
                    {
                        Level = 100;
                    }

                    // Recreate game over buttons cleanly
                    RetryIcon = new Fruit();
                    GameOverExitIcon = new Fruit();

                    // Start fresh gameplay setup
                    DrawGameOver();

                    // Resume music
                    if (IsToolActive())
                        audio.PlayGameplayMusic();
                }
            }

            if (isMenu)
            {
                startAngle += 5;
                exitAngle -= 5;

                if (StartIconState == 1)
                {
                    StartIcon.Y += 50;
                }


                if (StartIcon.Y > this.ClientSize.Height)
                {
                    isMenu = false;
                    StartIcon = null;
                    StartGame();
                }
            }

            if (isGame && !isOver)
            {
                // Lock before using Level
                int currentLevel;
                lock (levelLock)
                {
                    currentLevel = Level;
                }

                if (ct % speed == 0)
                {
                    int evenIndex = R.Next(8) * 2;
                    CreateFruit(evenIndex, R.Next(50, this.ClientSize.Width - 100));
                }

                if (ct % Level == 0)
                {
                    CreateBomb(R.Next(50, this.ClientSize.Width - 100));
                }
                ct++;

                float gravity = 2.2f;

                for (int i = 0; i < Fruits.Count; i++)
                {
                    Fruits[i].X += (int)Fruits[i].Vx;

                    Fruits[i].Y += (int)Fruits[i].Vy;

                    Fruits[i].Vy += gravity;
                }

                for (int i = 0; i < Bombs.Count; i++)
                {
                    Bombs[i].X += (int)Bombs[i].Vx;

                    Bombs[i].Y += (int)Bombs[i].Vy;

                    Bombs[i].Vy += gravity;
                }
            }


            DrawDubb(this.CreateGraphics());
        }

    }

    internal sealed class GameAudioPlayer : IDisposable
    {
        private readonly object audioLock = new object();
        private readonly Random random = new Random();
        private WaveOutEvent? musicOutput;
        private AudioFileReader? musicReader;
        private string currentMusicPath = "";
        private bool loopMusic;
        private bool disposed;

        public void PlayStartMusic()
        {
            PlayLoop(AppConfig.GetAssetPath("Start.mp3"));
        }

        public void PlayGameplayMusic()
        {
            PlayLoop(AppConfig.GetAssetPath("gameplay.mp3"));
        }

        public void StopMusic()
        {
            lock (audioLock)
            {
                StopMusicLocked();
            }
        }

        public void PauseMusic()
        {
            lock (audioLock)
            {
                musicOutput?.Pause();
            }
        }

        public void PlayFruitHit(bool useStickSound)
        {
            PlayEffect(AppConfig.GetAssetPath(useStickSound ? "hit.mp3" : "slash.mp3"));
        }

        public void PlayExplosion()
        {
            int effectNumber = random.Next(1, 4);
            PlayEffect(AppConfig.GetAssetPath($"explosion {effectNumber}.mp3"));
        }

        private void PlayLoop(string path)
        {
            if (!File.Exists(path))
                return;

            lock (audioLock)
            {
                if (disposed)
                    return;

                if (string.Equals(currentMusicPath, path, StringComparison.OrdinalIgnoreCase) && musicOutput != null)
                {
                    if (musicOutput.PlaybackState != PlaybackState.Playing)
                        musicOutput.Play();
                    return;
                }

                StopMusicLocked();
                currentMusicPath = path;
                loopMusic = true;
                musicReader = new AudioFileReader(path);
                musicOutput = new WaveOutEvent();
                musicOutput.Init(musicReader);
                musicOutput.PlaybackStopped += (_, _) =>
                {
                    lock (audioLock)
                    {
                        if (!loopMusic || musicReader == null || musicOutput == null)
                            return;

                        musicReader.Position = 0;
                        musicOutput.Play();
                    }
                };
                musicOutput.Play();
            }
        }

        private void PlayEffect(string path)
        {
            if (!File.Exists(path))
                return;

            lock (audioLock)
            {
                if (disposed)
                    return;
            }

            try
            {
                var reader = new AudioFileReader(path);
                var output = new WaveOutEvent();
                output.Init(reader);
                output.PlaybackStopped += (_, _) =>
                {
                    output.Dispose();
                    reader.Dispose();
                };
                output.Play();
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Sound effect error: {ex.Message}");
            }
        }

        private void StopMusicLocked()
        {
            loopMusic = false;
            currentMusicPath = "";
            if (musicOutput != null)
            {
                musicOutput.Stop();
                musicOutput.Dispose();
                musicOutput = null;
            }
            musicReader?.Dispose();
            musicReader = null;
        }

        public void Dispose()
        {
            lock (audioLock)
            {
                disposed = true;
                StopMusicLocked();
            }
        }
    }
}