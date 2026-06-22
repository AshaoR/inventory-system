"""桌面应用入口 — pywebview 包装 Flask"""
import threading
import time
import urllib.request
import sys
import webview

from run import app, init_db

FLASK_URL = "http://127.0.0.1:5000"


def _wait_for_server(url, timeout=8):
    for i in range(timeout * 2):
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def _start_flask():
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    with app.app_context():
        init_db()

    t = threading.Thread(target=_start_flask, daemon=True)
    t.start()

    if not _wait_for_server(FLASK_URL):
        print("Flask 服务启动失败", file=sys.stderr)
        sys.exit(1)

    webview.create_window(
        "紫洋玩具 — 库存管理系统",
        FLASK_URL,
        width=1280,
        height=800,
        min_size=(960, 600),
        confirm_close=True,
    )
    webview.start()
