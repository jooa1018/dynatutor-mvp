"""Synthetic-only Stage 6 fixtures. No textbook or held-out corpus assets."""
from __future__ import annotations

from io import BytesIO
from math import cos, pi, sin

from PIL import Image, ImageDraw


def _encode(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def incline_diagram(*, angle_label: str = "30°", force_label: str = "10 N") -> bytes:
    image = Image.new("RGB", (640, 420), "white")
    draw = ImageDraw.Draw(image)
    draw.line((80, 340, 560, 160), fill="black", width=5)
    draw.rectangle((290, 220, 390, 300), outline="black", width=4)
    draw.line((340, 250, 450, 210), fill="black", width=4)
    draw.polygon(((450, 210), (435, 207), (442, 221)), fill="black")
    draw.text((455, 185), force_label, fill="black")
    draw.arc((80, 280, 180, 380), 270, 338, fill="black", width=3)
    draw.text((145, 320), angle_label, fill="black")
    return _encode(image)


def pulley_diagram(*, left_label: str = "2 kg", right_label: str = "3 kg") -> bytes:
    image = Image.new("RGB", (640, 420), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((250, 45, 390, 185), outline="black", width=5)
    draw.line((250, 115, 250, 320), fill="black", width=4)
    draw.line((390, 115, 390, 320), fill="black", width=4)
    draw.rectangle((205, 300, 295, 380), outline="black", width=4)
    draw.rectangle((345, 300, 435, 380), outline="black", width=4)
    draw.text((220, 335), left_label, fill="black")
    draw.text((360, 335), right_label, fill="black")
    return _encode(image)


def free_body_diagram(*, normal_label: str = "N", weight_label: str = "mg") -> bytes:
    image = Image.new("RGB", (520, 420), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((210, 170, 310, 270), outline="black", width=4)
    draw.line((260, 170, 260, 70), fill="black", width=4)
    draw.polygon(((260, 60), (252, 78), (268, 78)), fill="black")
    draw.text((275, 80), normal_label, fill="black")
    draw.line((260, 270, 260, 370), fill="black", width=4)
    draw.polygon(((260, 380), (252, 362), (268, 362)), fill="black")
    draw.text((275, 340), weight_label, fill="black")
    return _encode(image)


__all__ = ["free_body_diagram", "incline_diagram", "pulley_diagram"]
