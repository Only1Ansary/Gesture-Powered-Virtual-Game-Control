namespace FruitNinjaGame
{
    internal static class Program
    {
        /// <summary>
        ///  The main entry point for the application.
        /// </summary>
        [STAThread]
        static void Main()
        {
            Application.ThreadException += (_, e) => LogFatal("UI thread exception", e.Exception);
            AppDomain.CurrentDomain.UnhandledException += (_, e) =>
                LogFatal("Unhandled exception", e.ExceptionObject as Exception);

            try
            {
                // To customize application configuration such as set high DPI settings or default font,
                // see https://aka.ms/applicationconfiguration.
                ApplicationConfiguration.Initialize();
                Application.Run(new GUIForm());
            }
            catch (Exception ex)
            {
                LogFatal("Startup exception", ex);
            }
        }

        private static void LogFatal(string title, Exception? ex)
        {
            try
            {
                string msg = $"{DateTime.Now:O} {title}\n{ex}\n\n";
                string path = Path.Combine(AppContext.BaseDirectory, "startup_error.log");
                File.AppendAllText(path, msg);
                MessageBox.Show(
                    $"{title}\n\n{ex?.Message}\n\nSee startup_error.log for details.",
                    "FruitNinjaGame Error",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
            catch
            {
                // Avoid throwing while handling a fatal exception.
            }
        }
    }
}