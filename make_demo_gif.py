"""Render demo/demo.gif from the real transcripts in demo/ (produced by seance.py with Gemma 3 4B)."""
import textwrap

from PIL import Image, ImageDraw, ImageFont

W, H, PAD, LH = 1000, 660, 22, 20
BG, FG, DIM, GHOST, GOLD, WARN = (14, 12, 20), (226, 222, 232), (128, 122, 145), (176, 214, 255), (242, 178, 64), (240, 120, 90)
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 14)
bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 14)
MAXC = 112

frames, durations, screen = [], [], []


def frame(lines):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    for i, (text, color, f) in enumerate(lines[-((H - 2 * PAD) // LH):]):
        d.text((PAD, PAD + i * LH), text, fill=color, font=f)
    return im


def show(ms):
    frames.append(frame(screen))
    durations.append(ms)


def typed(cmd):
    for i in list(range(2, len(cmd), 4)) + [len(cmd)]:
        screen[-1:] = [(cmd[:i], FG, bold)]
        show(45)


def color_of(line):
    s = line.strip()
    if s.startswith(("╭", "│", "╰")):
        return GOLD
    if s.startswith("👻") or (screen and screen[-1][1] == GHOST and s and not s.startswith(("📜", "⚠", "("))):
        return GHOST
    if "⚠" in s:
        return WARN
    if s.startswith("🕯") or s.startswith("📜"):
        return DIM
    return FG


def emit(path, per_line=110, hold=3500):
    for raw in open(path, encoding="utf-8").read().splitlines():
        raw = raw.replace("🕯", "*").replace("👻", ">").replace("📜", "#")
        parts = textwrap.wrap(raw, MAXC, subsequent_indent="   ") or [""]
        for p in parts:
            c = GHOST if raw.startswith(">") else (GOLD if raw.strip()[:1] in "╭│╰" else
                                                  WARN if "⚠" in raw else DIM if raw.startswith(("*", "#")) else FG)
            screen.append((p, c, font))
            show(per_line)
    show(hold)


screen[:] = [("$ python seance.py epitaph left-pad", FG, bold)]
typed("$ python seance.py epitaph left-pad")
screen.append(("   … Gemma 3 4B, local, 2 CPU cores, no network (sped up) …", DIM, font)); show(900)
emit("demo/epitaph.txt", per_line=140, hold=4200)

for q, f in [("Why did you change hands in 2016?", "demo/ask-hands.txt"),
             ("Who gave you a license, and which one?", "demo/ask-license.txt"),
             ("What was your favourite food?", "demo/ask-food.txt")]:
    screen[:] = [("", FG, bold)]
    typed(f'$ python seance.py ask left-pad "{q}"')
    screen.append(("   … the medium listens (~1 min on CPU, sped up) …", DIM, font)); show(700)
    emit(f, hold=4500)

frames[0].save("demo/demo.gif", save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)
print("demo/demo.gif", len(frames), "frames")
