# Spike S1, run 2: fresh PowerPoint process, screenshots of slides with add-ins.
param(
  [string]$Pptx = "$PSScriptRoot\probe.pptx",
  [string]$Log = "http://127.0.0.1:8471/log"
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms, System.Drawing

function Mark($ev, $data) {
  $body = @{ iid = "driver"; ev = $ev; t = [DateTimeOffset]::Now.ToUnixTimeMilliseconds(); data = $data } | ConvertTo-Json -Compress
  try { Invoke-RestMethod -Uri $Log -Method Post -Body $body -ContentType "application/json" | Out-Null } catch { }
  "{0:HH:mm:ss.fff} {1} {2}" -f (Get-Date), $ev, $data
}
function Shot($name) {
  $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
  $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
  New-Item -ItemType Directory -Force "$PSScriptRoot\shots" | Out-Null
  $bmp.Save("$PSScriptRoot\shots\$name.png", [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
  Mark "shot" $name
}

$app = New-Object -ComObject PowerPoint.Application
$pres = $app.Presentations.Open((Resolve-Path $Pptx).Path, -1, 0, -1)
$settings = $pres.SlideShowSettings
$settings.ShowPresenterView = 0
$win = $settings.Run()
Mark "slideshow-start" 1
Start-Sleep -Seconds 4
foreach ($i in 2, 3, 5) {
  $win.View.GotoSlide($i)
  Mark "goto" $i
  Start-Sleep -Seconds 4
  Shot "slide$i"
}
$win.View.Exit()
Start-Sleep -Seconds 3
Shot "edit-view"
$pres.Close()
$app.Quit()
Mark "quit" 0
