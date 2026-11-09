"""Make the layers that bring her portrait to life (ui/Avatar.qml), from design/images/cobra-avatar.png:

    cobra-eyes.png    just her glowing eyes, white, for tinting to the state colour
    cobra-lids.png    her eyes closed (skin over the eyes and a lash line), for blinking
    cobra-scales.png  the neon scales, white, where the shimmer shows

Run with the Cobra venv's Python (it has Pillow) after changing the portrait.
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent.parent / "images"
# each eye's outline, traced by hand (the glowing cheek around them is the same red)
EYES = [
    [(131, 194), (140, 191), (151, 190), (163, 191), (173, 194), (180, 198), (185, 203),
     (178, 208), (168, 210), (152, 210), (140, 207), (133, 200)],
    [(266, 193), (272, 184), (282, 176), (294, 172), (306, 170), (320, 170), (333, 171),
     (336, 175), (328, 182), (319, 188), (305, 193), (290, 195), (276, 196)],
]


def main() -> None:
    src = Image.open(HERE / "cobra-avatar.png").convert("RGB")
    w, h = src.size

    outline = Image.new("L", (w, h), 0)
    for eye in EYES:
        ImageDraw.Draw(outline).polygon(eye, fill=255)
    # inside the outline, how bright the red is says how much is eye
    red = src.getchannel("R").point(lambda v: max(0, min(255, (v - 120) * 2)))
    eyes = ImageChops.multiply(outline.filter(ImageFilter.GaussianBlur(1.0)), red)
    eyes = eyes.filter(ImageFilter.GaussianBlur(0.8))
    white = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    white.putalpha(eyes)
    white.save(HERE / "cobra-eyes.png")

    # closed eyes: skin from just below each eye moved up over it, a little darker, and a lash
    # line curving along the lower part of the eye
    lids = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    lid_mask = outline.filter(ImageFilter.MaxFilter(5))
    for eye in EYES:
        xs = [p[0] for p in eye]
        ys = [p[1] for p in eye]
        box = (min(xs) - 4, min(ys) - 4, max(xs) + 5, max(ys) + 5)
        height = box[3] - box[1]
        skin = src.crop((box[0], box[1] + height, box[2], box[3] + height))
        skin = skin.point(lambda v: int(v * 0.82))
        patch = Image.new("RGBA", skin.size, (0, 0, 0, 0))
        patch.paste(skin, (0, 0))
        patch.putalpha(lid_mask.crop(box).filter(ImageFilter.GaussianBlur(1.2)))
        lids.alpha_composite(patch, (box[0], box[1]))
        left = min(eye)
        right = max(eye)
        bottom = max(ys)
        sag = (bottom - (left[1] + right[1]) / 2) * 0.55
        line = []
        for i in range(21):
            t = i / 20
            x = left[0] + (right[0] - left[0]) * t
            y = left[1] + (right[1] - left[1]) * t + sag * 4 * t * (1 - t)
            line.append((x, y))
        lash = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(lash).line(line, fill=(30, 2, 6, 235), width=3, joint="curve")
        lids.alpha_composite(lash.filter(ImageFilter.GaussianBlur(0.7)))
    lids.save(HERE / "cobra-lids.png")

    scales = Image.new("L", (w, h), 0)
    sp = scales.load()
    px = src.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if g > 110 and g > r * 0.75:
                sp[x, y] = min(255, (g - 90) * 2)
    scales = scales.filter(ImageFilter.GaussianBlur(1.5))
    out = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    out.putalpha(scales)
    out.save(HERE / "cobra-scales.png")


if __name__ == "__main__":
    main()
