"""Draws the bespoke GOODTIMES wordmark as SVG (no fonts).

Each letter is a centerline skeleton; the tube look comes from stacking
round-capped strokes of decreasing width along the same skeleton.
Run: python3 logo/build_goodtimes.py
"""
import math
from pathlib import Path

OUT = Path(__file__).parent
W = 44            # tube width (outer)
H2 = W / 2
TOP, BOT = 40 + H2, 240 - H2    # skeleton top / bottom, cap height 200
CY = (TOP + BOT) / 2
RY = (BOT - TOP) / 2
GAP = 10          # space between letters' outer edges


def pt(cx, rx, deg):
    a = math.radians(deg)
    return cx + rx * math.cos(a), CY + RY * math.sin(a)


def letter_O():
    rx = 62
    cx = H2 + rx
    return 2 * cx, [f"M {cx - rx} {CY} A {rx} {RY} 0 1 1 {cx + rx} {CY} A {rx} {RY} 0 1 1 {cx - rx} {CY}"]


def letter_G():
    rx = 62
    cx = H2 + rx
    x1, y1 = pt(cx, rx, -38)      # upper-right terminal
    x2, y2 = pt(cx, rx, 8)        # right side, just below center
    return 2 * cx, [
        f"M {x1:.1f} {y1:.1f} A {rx} {RY} 0 1 0 {x2:.1f} {y2:.1f} L {cx + 10} {y2:.1f}"
    ]


def letter_D():
    r = RY
    stem = H2
    flat = 40
    return stem + flat + r + H2, [
        f"M {stem} {TOP} H {stem + flat} A {r} {r} 0 0 1 {stem + flat} {BOT} H {stem} Z"
    ]


def letter_T():
    w = 128
    return w + W, [f"M {H2} {TOP} H {H2 + w}", f"M {H2 + w / 2} {TOP} V {BOT}"]


def letter_I():
    return W, [f"M {H2} {TOP} V {BOT}"]


def letter_M():
    w = 150
    l, r = H2, H2 + w
    return w + W, [f"M {l} {BOT} V {TOP} L {(l + r) / 2} {BOT - 50} L {r} {TOP} V {BOT}"]


def letter_E():
    w = 112
    return w + W, [f"M {H2 + w} {TOP} H {H2} V {BOT} H {H2 + w}", f"M {H2} {CY} H {H2 + w - 18}"]


def letter_S():
    # Two opposed bowls meeting at the spine.
    l, r = H2 + 2, H2 + 120
    m = (l + r) / 2
    return r + H2, [
        f"M {r - 4} {TOP + 28} "
        f"C {r - 22} {TOP + 6}, {m + 22} {TOP}, {m} {TOP} "
        f"C {l + 22} {TOP}, {l} {TOP + 20}, {l} {TOP + 44} "
        f"C {l} {CY - 12}, {l + 30} {CY - 4}, {m} {CY + 2} "
        f"C {r - 30} {CY + 8}, {r} {CY + 18}, {r} {BOT - 44} "
        f"C {r} {BOT - 18}, {m + 24} {BOT}, {m} {BOT} "
        f"C {l + 24} {BOT}, {l + 6} {BOT - 10}, {l - 2} {BOT - 26}"
    ]


LETTERS = {"G": letter_G, "O": letter_O, "D": letter_D, "T": letter_T,
           "I": letter_I, "M": letter_M, "E": letter_E, "S": letter_S}

# Tube layers, outermost first: (width, color key)
TUBE = [(W, "edge"), (W - 8, "body"), (W - 20, "light"), (W - 28, "body"), (5, "shine")]
PALETTE = {"edge": "#B8344A", "body": "#E07C8C", "light": "#F3B3BD", "shine": "#FFF1F3"}
FLAT = "#D46A7A"


def layout(word="GOODTIMES"):
    x, glyphs = 0, []
    for ch in word:
        w, paths = LETTERS[ch]()
        glyphs.append((x, paths))
        x += w + GAP
    return x - GAP, glyphs


# Marquee animation, one entry per letter of GOODTIMES: (blip cycle s, start offset s, sways).
# Cycles are mismatched so the letters never fall into a visible rhythm; the I is the bad tube.
FLICKER = [(22, -3, False), (26, -17, True), (34, -1, False), (19, -9, False),
           (38, -24, True), (0, 0, False), (24, -13, False), (30, -6, True), (21, -19, False)]
FAULTY = 5
NEON_CSS = """
.gt-tubes { animation: gt-glow 4.5s ease-in-out infinite; }
.gt-l { animation: gt-blip var(--d) linear var(--o) infinite; transform-box: fill-box; transform-origin: 50% 100%; }
.gt-l.gt-sway { animation: gt-blip var(--d) linear var(--o) infinite, gt-sway 5.5s ease-in-out var(--o) infinite; }
.gt-l.gt-faulty { animation: gt-faulty 7s linear -2s infinite; }
@keyframes gt-glow { 0%, 100% { filter: drop-shadow(0 0 3px rgba(224, 96, 120, .35)); } 50% { filter: drop-shadow(0 0 9px rgba(224, 96, 120, .6)); } }
@keyframes gt-blip { 0%, 91%, 91.6%, 92.3%, 100% { opacity: 1; } 91.3% { opacity: .3; } 91.9% { opacity: .55; } }
@keyframes gt-faulty { 0%, 18%, 19.4%, 21%, 24.6%, 58%, 69.4%, 71%, 100% { opacity: 1; } 18.7% { opacity: .25; } 20% { opacity: .35; } 21.6%, 24% { opacity: .3; } 58.6%, 68.8% { opacity: .22; } 70.2% { opacity: .5; } }
@keyframes gt-sway { 0%, 100% { transform: none; } 30% { transform: rotate(.8deg) translateY(-1px); } 65% { transform: rotate(-.6deg); } }
@media (prefers-reduced-motion: reduce) { .gt-tubes, .gt-l, .gt-l.gt-sway, .gt-l.gt-faulty { animation: none; } }
"""


def svg(layers, pad=30, bg="#FFFFFF", animate=False):
    width, glyphs = layout()
    vw, vh = width + 2 * pad, 200 + 2 * pad
    letters = []
    for i, (x, paths) in enumerate(glyphs):
        d = "".join(f'<path d="{p}"/>' for p in paths)
        tube = "".join(f'<g stroke="{c}" stroke-width="{w}">{d}</g>' for w, c in layers)
        attrs = ""
        if animate:
            cycle, offset, sways = FLICKER[i]
            cls = "gt-l gt-faulty" if i == FAULTY else "gt-l gt-sway" if sways else "gt-l"
            attrs = f' class="{cls}" style="--d:{cycle}s;--o:{offset}s"'
        letters.append(f'<g transform="translate({x + pad:.1f} {pad - 40})"><g{attrs}>{tube}</g></g>')
    style = f"  <style>{NEON_CSS}  </style>\n" if animate else ""
    body = "\n    ".join(letters)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vw:.0f} {vh}" role="img" aria-label="GOODTIMES">\n'
        f'{style}'
        f'  <rect width="100%" height="100%" fill="{bg}"/>\n'
        f'  <g class="gt-tubes" fill="none" stroke-linecap="round" stroke-linejoin="round">\n    {body}\n  </g>\n</svg>\n'
    )


if __name__ == "__main__":
    tube = [(w, PALETTE[c]) for w, c in TUBE]
    (OUT / "goodtimes.svg").write_text(svg(tube))
    (OUT / "goodtimes-neon.svg").write_text(svg(tube, animate=True))
    (OUT / "goodtimes-flat.svg").write_text(svg([(W, FLAT)]))
    print("wrote goodtimes.svg, goodtimes-neon.svg, goodtimes-flat.svg")
