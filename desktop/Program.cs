using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace NanoCut {
    internal class RuntimeSettings {
        public string python { get; set; }
        public string[] paths { get; set; }
    }

    internal sealed class Editor : Form {
        private readonly WebView2 view = new WebView2 { Dock = DockStyle.Fill };
        private Process engine;
        private bool allowClose;
        private bool checkingClose;
        private bool ready;
        private readonly string dataDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "NanoCutRuntime");

        public Editor() {
            Text = "NanoCut 1.1.0.1";
            ClientSize = new Size(1360, 850);
            StartPosition = FormStartPosition.CenterScreen;
            Controls.Add(view);
            Shown += async (_, __) => {
                try { await StartEditor(); }
                catch (Exception ex) {
                    if (IsDisposed) return;
                    MessageBox.Show(this, ex.Message + "\n\nRun NanoCut 1.1.0.1 Setup to repair the installation.", Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
                    allowClose = true;
                    Close();
                }
            };
            FormClosing += async (_, e) => {
                if (allowClose || !ready) return;
                e.Cancel = true;
                if (checkingClose) return;
                checkingClose = true;
                try {
                    string dirty = await view.ExecuteScriptAsync("typeof ed !== 'undefined' && (ed.dirty || taskRunning)");
                    if (dirty == "true" && MessageBox.Show(this, "Close the editor and stop any active task?", Text, MessageBoxButtons.OKCancel) != DialogResult.OK) return;
                    allowClose = true;
                    BeginInvoke(new Action(Close));
                } catch { allowClose = true; BeginInvoke(new Action(Close)); }
                finally { checkingClose = false; }
            };
            FormClosed += (_, __) => {
                if (engine != null) {
                    try { engine.StandardInput.Close(); } catch (InvalidOperationException) { }
                    engine.Dispose();
                }
            };
        }

        private async Task StartEditor() {
            var config = new JavaScriptSerializer().Deserialize<RuntimeSettings>(File.ReadAllText(Path.Combine(dataDir, "runtime-1.1.json")));
            string app = AppDomain.CurrentDomain.BaseDirectory;
            var start = new ProcessStartInfo(config.python, "-u \"NanoCut.py\" --desktop-worker") {
                WorkingDirectory = app, UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true
            };
            start.EnvironmentVariables["PATH"] = string.Join(";", config.paths) + ";" + Environment.GetEnvironmentVariable("PATH");
            start.EnvironmentVariables["NANOCUT_INSTALLED"] = "1";
            engine = Process.Start(start);
            engine.ErrorDataReceived += (_, e) => Debug.WriteLine(e.Data);
            engine.BeginErrorReadLine();
            var line = engine.StandardOutput.ReadLineAsync();
            if (await Task.WhenAny(line, Task.Delay(30000)) != line) throw new IOException("The media engine timed out.");
            Uri url;
            if (!Uri.TryCreate(await line, UriKind.Absolute, out url) || url.Scheme != "http" || url.Host != "127.0.0.1")
                throw new IOException("The media engine could not start.");
            var environment = await CoreWebView2Environment.CreateAsync(null, Path.Combine(dataDir, "WebView2"));
            await view.EnsureCoreWebView2Async(environment);
            view.CoreWebView2.NavigationStarting += (_, e) => {
                if (!e.Uri.StartsWith(url.AbsoluteUri, StringComparison.Ordinal)) e.Cancel = true;
            };
            view.CoreWebView2.NewWindowRequested += (_, e) => {
                e.Handled = true;
                if (e.Uri.StartsWith("https://www.tiktok.com/", StringComparison.OrdinalIgnoreCase) || e.Uri == "https://github.com/Interprole/NanoCut/releases/latest")
                    Process.Start(new ProcessStartInfo(e.Uri) { UseShellExecute = true });
            };
            view.CoreWebView2.NavigationCompleted += (_, e) => {
                ready = e.IsSuccess;
                if (ready) Text = "NanoCut 1.1.0.1 — Editor";
            };
            view.Source = url;
        }

        [STAThread] public static int Main(string[] args) {
            if (args.Contains("--check-webview")) {
                try { return string.IsNullOrEmpty(CoreWebView2Environment.GetAvailableBrowserVersionString()) ? 1 : 0; }
                catch { return 1; }
            }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new Editor());
            return 0;
        }
    }
}
