# SPDX-License-Identifier: Apache-2.0
"""Regenerate the original silent clip. Optional tools: Pillow and ffmpeg on PATH."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math, shutil, subprocess, tempfile

HERE = Path(__file__).resolve().parent
W, H, FPS, SECONDS = 1280, 720, 24, 9
GREEN, INK, GOLD = "#176B57", "#183A43", "#DDAA37"

def font(size):
    for name in ("DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    raise RuntimeError("Install DejaVu Sans or edit font() to use a local TrueType font.")

def frame(t):
    im = Image.new("RGB", (W,H), "#EAF4EE")
    d = ImageDraw.Draw(im)
    d.text((W/2,65), "A bag for our picnic", font=font(48), fill=INK, anchor="mm")
    d.line((100,560,1180,560), fill=GREEN, width=4)
    # Items settle above the open bag in sequence, then the lid closes.
    for i,(name,col) in enumerate((("FRUIT","#D86E4C"),("WATER","#549CC5"),("BLANKET",GOLD))):
        f = max(0,min(1,(t-(1+i*1.6))/1.1))
        if f <= 0: continue
        y = 205+180*(1-(1-f)**3)
        x = 390+i*250
        d.rounded_rectangle((x-100,y-55,x+100,y+55),radius=15,fill=col)
        d.text((x,y),name,font=font(26),fill=INK,anchor="mm")
    # Basket front covers items as they land; labels remain visible until the lid.
    d.rounded_rectangle((270,415,1010,560),radius=18,fill=GREEN)
    d.text((640,490),"Ready to share",font=font(40),fill="white",anchor="mm")
    for x in range(300,1000,40):
        d.line((x,530,x+20,550), fill="#428875",width=3)
    if t>=6.7:
        f=min(1,(t-6.7)/.8)
        d.rounded_rectangle((260,400,1020,400+24*f),radius=8,fill=GOLD)
    d.text((640,630),"Fruit + water + a blanket",font=font(30),fill=INK,anchor="mm")
    d.rectangle((100,680,100+1080*min(1,t/SECONDS),686),fill=GOLD)
    return im

def main():
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required to regenerate packing.mp4")
    frame(6.5).save(HERE/"packing-poster.jpg",quality=93)
    with tempfile.TemporaryDirectory(prefix="texstage-media-") as temp:
        for n in range(FPS*SECONDS):
            frame(n/FPS).save(Path(temp)/f"{n:04}.png")
        subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y",
            "-framerate",str(FPS),"-i",str(Path(temp)/"%04d.png"),
            "-c:v","libx264","-pix_fmt","yuv420p","-crf","21","-movflags","+faststart",
            "-an",str(HERE/"packing.mp4")],check=True)
    print("Created 9-second H.264 clip and poster (original artwork; no audio).")

if __name__ == "__main__":
    main()
