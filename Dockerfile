# ai-chan Dockerfile (再現性保全 / Reproducibility Preservation)
#
# 目的:
#   10 年運用を見据えた "凍結された実行環境の証拠保全" 用コンテナ。
#   普段は Intel Mac のローカル venv (Python 3.9) で動かし、Docker は
#   「いつでも当時の実行環境を再現できる」ことを保証するための保全 image。
#
# 本番デプロイ用ではない。
#
# 使い方:
#   docker build -t aichan:$(git rev-parse --short HEAD) .
#   docker run --rm aichan:<sha>              # smoke (--help 相当)
#
# 注意:
#   - モデル (models/*.gguf) / ユーザーデータ (data/, logs/, personality/)
#     はイメージに含めない (.dockerignore 参照)
#   - hash-pinned な requirements/base.txt を使い、改ざん検知を兼ねる

FROM python:3.9-slim AS base

# ---- 環境変数 (再現性・静寂性) ----
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ---- 非 root ユーザー (uid 1000) ----
RUN groupadd --gid 1000 aichan \
    && useradd --uid 1000 --gid aichan --create-home --shell /bin/bash aichan

WORKDIR /app

# ---- 依存を先に入れて layer cache を効かせる ----
# hash-pinned された requirements/base.txt のみを先にコピーする
COPY requirements/base.txt /tmp/base.txt

# 層最小化: pip upgrade + hash 検証インストール + キャッシュ削除を 1 RUN に
RUN pip install --no-cache-dir --upgrade pip==24.2 \
    && pip install --no-cache-dir --require-hashes -r /tmp/base.txt \
    && rm -rf /tmp/base.txt /root/.cache/pip

# ---- アプリ本体 ----
COPY --chown=aichan:aichan . /app/

USER aichan

# smoke: --help 相当を ENTRYPOINT 化 (argparse の存在を保証する生存確認)
ENTRYPOINT ["python3", "-m", "core.ai_chan", "--help"]
