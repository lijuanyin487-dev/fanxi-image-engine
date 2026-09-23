from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from PIL import Image, ImageOps
from io import BytesIO

app = Flask(__name__)
CORS(app)

# 单张图片最大 30MB
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024


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

    try:
        # 读取原图
        image = Image.open(file.stream)

        # 自动修正手机/相机 EXIF 方向
        image = ImageOps.exif_transpose(image)

        # 当前测试阶段不做真实修图
        # 只重新编码为 PNG，证明图片真实经过后端
        image = image.convert("RGBA")

        output = BytesIO()
        image.save(output, format="PNG", optimize=False, compress_level=1)
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
