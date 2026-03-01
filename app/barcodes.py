import io
from barcode import Code128
from barcode.writer import ImageWriter
from PIL import Image

def generate_barcode_png(data: str) -> bytes:
    data = (data or "").strip()
    if not data:
        data = "0000000000"
    rv = io.BytesIO()
    code = Code128(data, writer=ImageWriter())
    code.write(rv, options={
        "module_width": 0.25,
        "module_height": 14.0,
        "font_size": 10,
        "text_distance": 3.0,
        "quiet_zone": 2.0,
    })
    rv.seek(0)
    img = Image.open(rv)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()
