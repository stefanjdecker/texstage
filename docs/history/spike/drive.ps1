# Spike S1: drive a PowerPoint slideshow over COM and mark every step in the probe log.
param(
  [string]$Pptx = "$PSScriptRoot\probe.pptx",
  [int]$Dwell = 6,
  [string]$Log = "http://127.0.0.1:8471/log",
  [switch]$InspectOnly
)
$ErrorActionPreference = "Stop"

function Mark($ev, $data) {
  $body = @{ iid = "driver"; ev = $ev; t = [DateTimeOffset]::Now.ToUnixTimeMilliseconds(); data = $data } | ConvertTo-Json -Compress
  try { Invoke-RestMethod -Uri $Log -Method Post -Body $body -ContentType "application/json" | Out-Null } catch { }
  "{0:HH:mm:ss.fff} {1} {2}" -f (Get-Date), $ev, $data
}

$app = New-Object -ComObject PowerPoint.Application
# Open(FileName, ReadOnly, Untitled, WithWindow)
$pres = $app.Presentations.Open((Resolve-Path $Pptx).Path, -1, 0, -1)
foreach ($s in $pres.Slides) {
  foreach ($sh in $s.Shapes) { Mark "shape" ("slide {0} id {1}: '{2}' type={3}" -f $s.SlideIndex, $s.SlideID, $sh.Name, $sh.Type) }
}
if ($InspectOnly) { $pres.Close(); return }

Start-Sleep -Seconds $Dwell          # editing view: do add-ins load here?
Mark "slideshow-start" 1
$settings = $pres.SlideShowSettings
$settings.ShowPresenterView = 0
$win = $settings.Run()
Start-Sleep -Seconds $Dwell
foreach ($i in 2..$pres.Slides.Count) {
  $win.View.GotoSlide($i)
  Mark "goto" $i
  Start-Sleep -Seconds $Dwell
}
foreach ($i in 2, 3) {               # revisit: same instance or a new one?
  $win.View.GotoSlide($i)
  Mark "goto" $i
  Start-Sleep -Seconds $Dwell
}
$win.View.Exit()
Mark "slideshow-exit" 0
Start-Sleep -Seconds $Dwell
$pres.Close()
Mark "closed" 0
