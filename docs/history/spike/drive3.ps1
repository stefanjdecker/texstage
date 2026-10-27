# Spike S1, run 3: capture the slideshow window itself (PrintWindow works even when it is covered).
param([string]$Pptx = "$PSScriptRoot\probe.pptx")
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class W {
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  public struct RECT { public int L, T, R, B; }
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  // the largest visible top-level window of a process = the slideshow
  public static IntPtr Largest(uint pid) {
    IntPtr best = IntPtr.Zero; long area = 0;
    EnumWindows((h, l) => { uint p; GetWindowThreadProcessId(h, out p); RECT r;
      if (p == pid && IsWindowVisible(h) && GetWindowRect(h, out r)) {
        long a = (long)(r.R - r.L) * (r.B - r.T); if (a > area) { area = a; best = h; } }
      return true; }, IntPtr.Zero);
    return best;
  }
}
"@
function Shot($hwnd, $name) {
  $r = New-Object W+RECT; [W]::GetClientRect($hwnd, [ref]$r) | Out-Null
  $bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
  $g = [System.Drawing.Graphics]::FromImage($bmp); $dc = $g.GetHdc()
  [W]::PrintWindow($hwnd, $dc, 3) | Out-Null   # PW_CLIENTONLY | PW_RENDERFULLCONTENT
  $g.ReleaseHdc($dc); $g.Dispose()
  New-Item -ItemType Directory -Force "$PSScriptRoot\shots" | Out-Null
  $bmp.Save("$PSScriptRoot\shots\$name.png", [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
  "shot $name"
}
$app = New-Object -ComObject PowerPoint.Application
$pres = $app.Presentations.Open((Resolve-Path $Pptx).Path, -1, 0, -1)
$settings = $pres.SlideShowSettings; $settings.ShowPresenterView = 0
$win = $settings.Run()
try {
Start-Sleep -Seconds 2
$hwnd = [W]::Largest([uint32](Get-Process POWERPNT | Select-Object -First 1).Id)
"slideshow hwnd $hwnd"
$win.Activate(); [W]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Seconds 3
foreach ($i in 2, 3) { $win.View.GotoSlide($i); Start-Sleep -Seconds 4; Shot $hwnd "w-slide$i" }
} finally { $win.View.Exit(); $pres.Close(); $app.Quit() }
"done"
