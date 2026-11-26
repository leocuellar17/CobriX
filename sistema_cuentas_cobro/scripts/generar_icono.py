"""Genera un ícono multi-resolución (assets/icono.ico) estilo Microsoft Fluent azul."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_OUT = BASE_DIR / "assets" / "icono.ico"


def generar_icono(destino: Path = ASSETS_OUT) -> Path:
    """Crea un ícono .ico con resoluciones 16x16, 32x32, 48x48 y 256x256."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fondo redondeado azul Microsoft (#0078D4)
    draw.rounded_rectangle(
        [(12, 12), (244, 244)],
        radius=54,
        fill=(0, 120, 212, 255),
    )

    # Borde superior sutil estilo Claymorfismo
    draw.rounded_rectangle(
        [(16, 16), (240, 240)],
        radius=50,
        outline=(110, 185, 245, 160),
        width=4,
    )

    # Símbolo $ centrado
    try:
        font = ImageFont.truetype("segoeui.ttf", 150)
    except OSError:
        try:
            font = ImageFont.truetype("arial.ttf", 150)
        except OSError:
            font = ImageFont.load_default()

    texto = "$"
    bbox = draw.textbbox((0, 0), texto, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size - text_w) / 2 - bbox[0]
    y = (size - text_h) / 2 - bbox[1] - 4
    draw.text((x, y), texto, font=font, fill=(255, 255, 255, 255))

    img.save(
        destino,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (256, 256)],
    )
    return destino


if __name__ == "__main__":
    ruta = generar_icono()
    print(f"Ícono generado exitosamente en: {ruta}")
