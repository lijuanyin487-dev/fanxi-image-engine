from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from PIL import Image, ImageOps
from io import BytesIO
from rembg import remove
import re

app = Flask(__name__)
CORS(app)

# 单张图片最大 30MB
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024


def normalize_hex_color(color: str) -> str:
    """
    支持:
    #FFFFFF
    FFFFFF
    #F3F3F3
    F3F3F3
    """
    if not color:
        return "#FFFFFF"

    color = color.strip()

    if not color.startswith("#"):
        color = "#" + color

    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        return "#FFFFFF"

    return color.upper()


def hex_to_rgb(hex_color: str):
    hex_color = normalize_hex_color(hex_color).lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


@app.get("/")
def home():
    return jsonify({
        "name": "FANXI Image Engine",
        "status": "running"
    })


@app.get("/health")
def health():
    return jsonify({
        "status": "ok"
    })


@app.post("/process")
def process_image():
    if "file" not in request.files:
        return jsonify({
            "success": False,
            "error": "No image uploaded"
        }), 400

    file = request.files["file"]

    if not file.filename:
        return jsonify({
            "success": False,
            "error": "Empty filename"
        }), 400

    # 新增：接收背景色
    bg_color = request.form.get("bg_color", "#FFFFFF")
    bg_color = normalize_hex_color(bg_color)

    try:
        # 读取原图
        image = Image.open(file.stream)

        # 自动修正 EXIF 方向
        image = ImageOps.exif_transpose(image)

        # 统一转 RGBA
        image = image.convert("RGBA")

        # 用 rembg 去背景，得到透明主体
        input_bytes = BytesIO()
        image.save(input_bytes, format="PNG", optimize=False, compress_level=1)
        input_bytes = input_bytes.getvalue()

        removed_bytes = remove(input_bytes)

        subject = Image.open(BytesIO(removed_bytes)).convert("RGBA")

        # 生成纯色背景
        rgb = hex_to_rgb(bg_color)
        background = Image.new("RGBA", subject.size, rgb + (255,))

        # 合成：主体叠加到纯色背景
        result = Image.alpha_composite(background, subject)

        output = BytesIO()
        result.save(output, format="PNG", optimize=False, compress_level=1)
        output.seek(0)

        return send_file(
            output,
            mimetype="image/png",
            as_attachment=False,
            download_name="fanxi-result.png"
        )

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
