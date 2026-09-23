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
# rembg 引擎
# -----------------------------

engine = {
    "ready": False,
    "loading": False,
    "error": None,
    "remove": None,
    "session": None,
}

engine_lock = threading.Lock()


def ensure_background_engine():
    """
    在当前 Gunicorn worker 中按需加载模型。
    第一次处理时加载，之后复用。
    """

    if engine["ready"]:
        return True

    with engine_lock:

        # 等锁期间，其他请求可能已经加载完成
        if engine["ready"]:
            return True

        engine["loading"] = True
        engine["error"] = None

        try:
            import onnxruntime as ort
            from rembg import remove, new_session

            print("Loading background engine...", flush=True)

            sess_opts = ort.SessionOptions()
            sess_opts.intra_op_num_threads = 1
            sess_opts.inter_op_num_threads = 1

            sess_opts.execution_mode = (
                ort.ExecutionMode.ORT_SEQUENTIAL
            )

            sess_opts.graph_optimization_level = (
                ort.GraphOptimizationLevel.ORT_DISABLE_ALL
            )

            session = new_session(
                "u2netp",
                sess_opts=sess_opts,
                providers=["CPUExecutionProvider"]
            )

            engine["remove"] = remove
            engine["session"] = session
            engine["ready"] = True
            engine["loading"] = False
            engine["error"] = None

            print(
                "Background removal engine is ready.",
                flush=True
            )

            return True

        except Exception as e:

            engine["ready"] = False
            engine["loading"] = False
            engine["error"] = str(e)

            print(
                "Background engine failed:",
                str(e),
                flush=True
            )

            return False


# -----------------------------
# 颜色
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

    hex_color = normalize_hex_color(
        hex_color
    ).lstrip("#")

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
        "status": "running"
    })


@app.get("/health")
def health():

    return jsonify({
        "status": "ok",
        "background_engine_ready": engine["ready"],
        "background_engine_loading": engine["loading"],
        "engine_error": engine["error"]
    })


@app.get("/warmup")
def warmup():
    """
    手动让当前服务进程加载模型。
    """

    success = ensure_background_engine()

    if success:
        return jsonify({
            "success": True,
            "background_engine_ready": True
        })

    return jsonify({
        "success": False,
        "background_engine_ready": False,
        "error": engine["error"]
    }), 500


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

    file = request.files["file"]

    if not file.filename:

        return jsonify({
            "success": False,
            "error": "Empty filename"
        }), 400


    # 第一次真正处理时加载模型
    if not ensure_background_engine():

        return jsonify({
            "success": False,
            "error": "Background engine failed",
            "engine_error": engine["error"]
        }), 500


    bg_color = normalize_hex_color(
        request.form.get(
            "bg_color",
            "#FFFFFF"
        )
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
