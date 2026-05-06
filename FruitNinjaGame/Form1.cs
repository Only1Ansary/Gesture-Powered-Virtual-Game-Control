namespace FruitNinjaGame
{
    public partial class Form1 : Form
    {
        System.Windows.Forms.Timer T = new System.Windows.Forms.Timer();
        Bitmap off;
        public Form1()
        {
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
                        create_explosion(Bombs[i].X, Bombs[i].Y);
                        animate_exp();
                        Bombs.RemoveAt(i);
                        LivesCount--;
                        if (LivesCount == 0)
                        {
                            isOver = true;
                            T.Stop();
                            Fruits.Clear();
                            Bombs.Clear();
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
        int LivesCount = 3;
        int prevX = -1;
        int prevY = -1;

        bool isMenu = true;
        bool isGame = false;
        bool isOver = false;

        float startAngle = 0;
        float exitAngle = 0;

        Bitmap back;
        Bitmap GameOver;
        Bitmap GameName;
        Bitmap StartRing;
        Bitmap ExitRing;

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
            pnn.img.Add(FruitImg[Type+1]);

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

            DrawScore();
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
            if(isOver)
            {
                GameOver = new Bitmap(AppConfig.GetAssetPath("GameOver.png"));
                g.DrawImage(GameOver, 0, 0, this.ClientSize.Width, this.ClientSize.Height);

                    
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

                if(ExitIconState == 0)
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

                int ones = ScoreCount % 10;
                int tens = (ScoreCount / 10) % 10;
                int hundreds = (ScoreCount / 100) % 10;
                int thousands = (ScoreCount / 1000) % 10;

                if (ScoreCount < 10)
                {
                    g.DrawImage(ScoreNum.First[ones], x, y, w, h);
                }
                else if (ScoreCount < 100)
                {
                    g.DrawImage(ScoreNum.First[tens], x, y, w, h);

                    g.DrawImage(ScoreNum.Second[ones], x + 40, y, w, h);
                }
                else if (ScoreCount < 1000)
                {
                    g.DrawImage(ScoreNum.First[hundreds], x, y, w, h);

                    g.DrawImage(ScoreNum.Second[tens], x + 40, y, w, h);

                    g.DrawImage(ScoreNum.Third[ones], x + 80, y, w, h);
                }
                else
                {
                    g.DrawImage(ScoreNum.First[thousands], x, y, w, h);

                    g.DrawImage(ScoreNum.Second[hundreds], x + 40, y, w, h);

                    g.DrawImage(ScoreNum.Third[tens], x + 80, y, w, h);

                    g.DrawImage(ScoreNum.Fourth[ones], x + 120, y, w, h);
                }
            }

            if (isGame)
            {
                for(int i = 0; i< Fruits.Count; i++)
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

            g.DrawImage(Blade.img[0], Blade.X, Blade.Y, Blade.img[0].Width - 150, Blade.img[0].Height - 150);

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

        private void Form1_Load(object? sender, EventArgs e)
        {
            off = new Bitmap(this.ClientSize.Width, this.ClientSize.Height);
            StartMenu();
            Bitmap img = new Bitmap(AppConfig.GetAssetPath("blade.png"));
            Blade.img.Add(img);
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
                if (ct % speed == 0)
                {
                    int evenIndex = R.Next(8) * 2;
                    CreateFruit(evenIndex, R.Next(50, this.ClientSize.Width - 100));
                }

                if(ct % Level == 0)
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


}
