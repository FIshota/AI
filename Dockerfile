# ai-chan Dockerfile (Phase 0.75)
#
# 目的: CI / 再現環境 / ポータブル開発環境の提供。
# 本番デプロイ用ではなく、"どの Mac/Linux でも同じ結果が出る" ための基盤。
#
# 使い方:
#   docker build -t ai-chan:0.75 .
#   docker run --rm -it ai-chan:0.75 python3 main.py --smoke-test
#
# 注意:
#   - モデル本体 (models/*.gguf) はイメージに含めない (サイズ・ライセンス)
#   - data/ logs/ personality/ も含めない (ユーザー固有)
#   - ボリュームマウントで持ち込む想定

FROM python:3.13-slim-bookworm AS base

# セキュリティ: 非 root ユーザー作成
RUN groupadd -r aichan && useradd -r -g aichan -m -d /home/aichan aichan

# Python パッケージビルドに必要な依存
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    curl \
    ca-certificates \
    # llama-cpp-python ビルド用
    libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 依存を先にインストール (layer cache 活用)
COPY requirements.txt requirements.lock ./

# requirements.lock があればそちらを優先 (hash-pinned)
RUN pip install --no-cache-dir --upgrade pip && \
    if [ -f requirements.lock ]; then \
        pip install --no-cache-dir --require-hashes -r requirements.lock || \
        pip install --no-cache-dir -r requirements.txt ; \
    else \
        pip install --no-cache-dir -r requirements.txt ; \
    fi

# アプリ本体
COPY --chown=aichan:aichan . /app/

# runtime dirs (空)
RUN mkdir -p data logs output reports backups models && \
    chown -R aichan:aichan /app

USER aichan

# smoke test をデフォルトに (安全)
CMD ["python3", "main.py", "--smoke-test"]


# ─── Developer stage (追加ツール) ─────────────────────────
FROM base AS dev

USER root
RUN pip install --no-cache-dir \
    pytest pytest-cov \
    ruff==0.8.4 black==24.10.0 isort==5.13.2 \
    bandit==1.8.0 pip-audit==2.7.3 \
    pip-licenses

USER aichan
CMD ["bash"]
