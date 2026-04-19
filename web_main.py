#!/usr/bin/env python3
"""
アイ Web API サーバー起動スクリプト
iPhone Safari からアイとおはなしするための Web サーバーです。

使い方:
  python web_main.py                    # デフォルト (port 8721)
  python web_main.py --port 3000        # ポート指定
  python main.py --web                  # main.py 経由
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))


def run_web_server(base_dir: Path, host: str = "0.0.0.0", port: int = 8721) -> None:
    """Web API サーバーを起動する。"""
    try:
        import uvicorn
    except ImportError:
        print("uvicorn が見つかりません。インストールしてください:")
        print("  pip install 'fastapi>=0.100' 'uvicorn[standard]>=0.23'")
        sys.exit(1)

    try:
        from web.app import create_app
    except ImportError as e:
        print(f"FastAPI モジュールの読み込みに失敗しました: {e}")
        print("  pip install 'fastapi>=0.100'")
        sys.exit(1)

    app = create_app(base_dir=base_dir)

    # LAN 上の IP アドレスを表示
    _show_access_info(host, port)

    uvicorn.run(app, host=host, port=port, log_level="info")


def _show_access_info(host: str, port: int) -> None:
    """アクセス用の URL を表示する。"""
    print("\n" + "=" * 50)
    print("  アイ Web API サーバー")
    print("=" * 50)
    print(f"  ローカル:   http://localhost:{port}")

    # LAN の IP を取得
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        print(f"  iPhone:     http://{ip}:{port}")
        print(f"\n  同じ Wi-Fi に接続した iPhone の Safari で")
        print(f"  上の URL を開いてください")
    except Exception:
        print(f"  ネットワーク: http://0.0.0.0:{port}")

    print("=" * 50 + "\n")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="アイ Web API サーバー")
    parser.add_argument("--host", default="0.0.0.0", help="バインドホスト")
    parser.add_argument("--port", type=int, default=8721, help="ポート番号")
    parser.add_argument(
        "--base-dir",
        default=str(BASE_DIR),
        help="ベースディレクトリ",
    )
    args = parser.parse_args()

    run_web_server(
        base_dir=Path(args.base_dir),
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
