# Launch from repo root: python -m src.server
import pathlib

from flask import Flask, jsonify

from .data_layer import DataLayer

_DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
_data = DataLayer(str(_DATA_DIR))
app = Flask(__name__)


@app.get("/item/<path:qid>")
def get_item(qid: str):
    item = _data.get(qid)
    if item is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(item)


@app.get("/health")
def health():
    return jsonify({"status": "ok", "itemCount": _data.count, "version": "1.0"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5310)
