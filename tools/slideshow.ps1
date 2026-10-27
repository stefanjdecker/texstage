<#
Drive a PowerPoint slideshow over COM, for testing the texquiz add-in (docs/design.md M4):

    .\slideshow.ps1 run deck.pptx "goto 2" "wait 3" "sim 20" "next" "wait 25" "shot q1" ... [-PresenterView]

opens the file read-only, starts the show, runs the steps, ends the show and closes the file
(and quits PowerPoint if it was not running before). One call for the whole test: PowerPoint
started by a script quits when that script ends.

Steps: "next"/"prev" (the clicker), "goto <n>", "wait <seconds>", "shot <name>" (PrintWindow of
the slideshow window into <Shots>\<name>.png, the presenter view into <name>-2.png - captures
them even when covered), "screen <name>" (what the screen shows there; "front" brings the show
in front first), "windows" (lists PowerPoint's windows), "sim <n>" (n simulated
phones join the game the deck plays - tools/simulate.py; stopped at the end), "results <name>"
(the game's CSV into <Shots>\<name>.csv).
#>
param(
  [Parameter(Position = 0, Mandatory)][ValidateSet("run")][string]$Command,
  [Parameter(Position = 1, Mandatory)][string]$Pptx,
  [Parameter(Position = 2, ValueFromRemainingArguments)][string[]]$Steps,
  [string]$Shots = ".",
  [string]$Server = "http://127.0.0.1:8470",
  [string]$Key = "",
  [switch]$PresenterView
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing @"
using System; using System.Drawing; using System.Runtime.InteropServices;
public static class TqWin {
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr c);
  public struct RECT { public int L, T, R, B; }
  // PowerShell is not DPI aware: on a monitor scaled to 150 % it sees 2560x1440 of a 3840x2160
  // screen and captures only that part. Measured and captured per monitor DPI aware instead.
  public static Bitmap Capture(IntPtr h, bool screen) {
    IntPtr old = SetThreadDpiAwarenessContext(new IntPtr(-4));     // PER_MONITOR_AWARE_V2
    try {
      RECT r;
      if (screen) GetWindowRect(h, out r); else GetClientRect(h, out r);
      Bitmap bmp = new Bitmap(r.R - r.L, r.B - r.T);
      using (Graphics g = Graphics.FromImage(bmp)) {
        if (screen) g.CopyFromScreen(r.L, r.T, 0, 0, bmp.Size);
        else { IntPtr dc = g.GetHdc(); PrintWindow(h, dc, 3); g.ReleaseHdc(dc); }   // PW_CLIENTONLY | PW_RENDERFULLCONTENT
      }
      return bmp;
    } finally { SetThreadDpiAwarenessContext(old); }
  }
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, System.Text.StringBuilder s, int n);
  // the slideshow's windows: the show (class screenClass), then the presenter view (PodiumParent)
  public static IntPtr[] Shows(uint pid) {
    var found = new System.Collections.Generic.List<IntPtr>();
    foreach (string cls in new[] { "screenClass", "PodiumParent" })
      EnumWindows((h, l) => { uint p; GetWindowThreadProcessId(h, out p);
        var c = new System.Text.StringBuilder(64); GetClassName(h, c, 64);
        if (p == pid && IsWindowVisible(h) && c.ToString() == cls) found.Add(h);
        return true; }, IntPtr.Zero);
    return found.ToArray();
  }
  public static string[] List(uint pid) {          // for "windows": class and size in pixels
    var found = new System.Collections.Generic.List<string>();
    IntPtr old = SetThreadDpiAwarenessContext(new IntPtr(-4));
    EnumWindows((h, l) => { uint p; GetWindowThreadProcessId(h, out p); RECT r;
      var c = new System.Text.StringBuilder(64); GetClassName(h, c, 64);
      if (p == pid && IsWindowVisible(h) && GetWindowRect(h, out r))
        found.Add(string.Format("{0} at {1},{2} {3}x{4}", c, r.L, r.T, r.R - r.L, r.B - r.T));
      return true; }, IntPtr.Zero);
    SetThreadDpiAwarenessContext(old);
    return found.ToArray();
  }
}
"@
$tools = Split-Path -Parent $PSScriptRoot
$python = Join-Path $tools ".venv\Scripts\python.exe"
if (-not $Key) { $Key = (Get-Content (Join-Path $HOME ".texquiz\presenter-key")).Trim() }

function Shot($name, [switch]$Screen) {
  $proc = Get-Process POWERPNT | Select-Object -First 1
  New-Item -ItemType Directory -Force $Shots | Out-Null
  $n = 0
  foreach ($hwnd in [TqWin]::Shows([uint32]$proc.Id)) {     # name.png, name-2.png (presenter view)
    $n++
    $file = Join-Path $Shots ($(if ($n -eq 1) { "$name.png" } else { "$name-$n.png" }))
    $bmp = [TqWin]::Capture($hwnd, [bool]$Screen)
    $bmp.Save($file, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
  }
  "  shot $name ($n windows)"
}

function Game($deck) {
  $decks = Invoke-RestMethod -Headers @{ "X-Texquiz-Key" = $Key } "$Server/api/decks"
  ($decks | Where-Object { $_.deck -eq $deck -and $_.game } | Select-Object -First 1).game
}

$started = -not (Get-Process POWERPNT -ErrorAction SilentlyContinue)
$app = New-Object -ComObject PowerPoint.Application
$pres = $app.Presentations.Open((Resolve-Path $Pptx).Path, -1, 0, -1)       # read-only, with window
$deck = [IO.Path]::GetFileNameWithoutExtension($Pptx).ToLower() -replace "[^a-z0-9]+", "-"
$pres.SlideShowSettings.ShowPresenterView = [int][bool]$PresenterView
$win = $pres.SlideShowSettings.Run()
$sims = @()
"slideshow of $($pres.Name): $($pres.Slides.Count) slides"
try {
  foreach ($step in $Steps) {
    $verb, $arg = $step -split " ", 2
    switch ($verb) {
      "next" { $win.View.Next() }
      "prev" { $win.View.Previous() }
      "goto" { $win.View.GotoSlide([int]$arg) }
      "wait" { Start-Sleep -Milliseconds ([int]([double]$arg * 1000)) }
      "shot" { Shot $arg }
      "screen" { Shot $arg -Screen }
      "front" { $win.Activate(); Start-Sleep -Milliseconds 500 }
      "windows" { [TqWin]::List([uint32](Get-Process POWERPNT | Select-Object -First 1).Id) | ForEach-Object { "  $_" } }
      "sim" {
        $game = Game $deck
        $ws = ($Server -replace "^http", "ws") + "/ws"
        $sims += Start-Process -PassThru -WindowStyle Hidden -FilePath $python -ArgumentList @(
          (Join-Path $PSScriptRoot "simulate.py"), "--pin", $game.pin, "--players", $arg, "--url", $ws, "--duration", "3600")
        "  $arg simulated phones join game $($game.pin)"
      }
      "results" {
        $game = Game $deck
        New-Item -ItemType Directory -Force $Shots | Out-Null
        Invoke-WebRequest -UseBasicParsing -Headers @{ "X-Texquiz-Key" = $Key } "$Server/api/results/$($game.session).csv" -OutFile (Join-Path $Shots "$arg.csv")
        "  results $arg.csv"
      }
      default { throw "unknown step $step" }
    }
    if ($verb -in "next", "prev", "goto") { "slide $($win.View.CurrentShowPosition) (id $($win.View.Slide.SlideID))" }
  }
} finally {
  foreach ($p in $sims) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
  if ($app.SlideShowWindows.Count -gt 0) { $app.SlideShowWindows.Item(1).View.Exit() }
  $pres.Close()
  if ($started) { $app.Quit() }
  "stopped"
}
