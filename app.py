from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from PIL import Image, ImageOps
from io import BytesIO
import threading
import re

app = Flask(__name__)
CORS(app)

app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024


# -----------------------------
# rembg 引擎状态
# -----------------------------

engine = {
    "ready": False,
    "error": None,
    "remove": None,
    "session": None,
}


def load_background_engine():
    """
    后台加载 rembg。
    不阻塞 Flask / Gunicorn 启动。
    """
    try:
        from rembg import remove, new_session

        # 使用轻量模型，更适合 Render Free
        session = new_session("u2netp")

        engine["remove"] = remove
        engine["session"] = session
        engine["ready"] = True
        engine["error"] = None

        print("Background removal engine is ready.")

    except Exception as e:
        engine["ready"] = False
        engine["error"] = str(e)
        print("Background engine failed:", str(e))


# 后台线程加载模型
threading.Thread(
    target=load_background_engine,
    daemon=True
).start()


# -----------------------------
# 颜色处理
# -----------------------------

def normalize_hex_color(color: str) -> str:
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

    return tuple(
        int(hex_color[i:i + 2], 16)
        for i in (0, 2, 4)
    )


# -----------------------------
# 基础接口
# -----------------------------

@app.get("/")
def home():
    return jsonify({
        "name": "FANXI Image Engine",
        "status": "running",
        "background_engine_ready": engine["ready"]
    })


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "background_engine_ready": engine["ready"],
        "engine_error": engine["error"]
    })


# -----------------------------
# 图片处理
# -----------------------------

@app.post("/process")
def process_image():

    if "file" not in request.files:
        return jsonify({
            "success": False,
            "error": "No image uploaded"
        }), 400

    if not engine["ready"]:
        return jsonify({
            "success": False,
            "error": "Background engine is warming up",
            "engine_error": engine["error"]
        }), 503

    file = request.files["file"]

    if not file.filename:
        return jsonify({
            "success": False,
            "error": "Empty filename"
        }), 400

    bg_color = normalize_hex_color(
        request.form.get("bg_color", "#FFFFFF")
    )

    try:

        image = Image.open(file.stream)
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGBA")

        input_buffer = BytesIO()

        image.save(
            input_buffer,
            format="PNG",
            optimize=False,
            compress_level=1
        )

        input_bytes = input_buffer.getvalue()

        # 真正去背景
        removed_bytes = engine["remove"](
            input_bytes,
            session=engine["session"]
        )

        subject = Image.open(
            BytesIO(removed_bytes)
        ).convert("RGBA")

        rgb = hex_to_rgb(bg_color)

        background = Image.new(
            "RGBA",
            subject.size,
            rgb + (255,)
        )

        result = Image.alpha_composite(
            background,
            subject
        )

        output = BytesIO()

        result.save(
            output,
            format="PNG",
            optimize=False,
            compress_level=1
        )

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
    app.run(
        host="0.0.0.0",
        port=10000
    )
