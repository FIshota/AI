"""
Web API サーバー（FastAPI）
AiChan コアをラップして iPhone Safari からアクセス可能にする。
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import hmac
import secrets

from fastapi import FastAPI, HTTPException, Request, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── B1 fix (2026-04-21): Bearer token 認証 ─────────────────────
# 環境変数 AICHAN_API_TOKEN を設定すると全 /api/* ルートに認証必須。
# 未設定時は localhost/127.0.0.1 からのリクエストのみ許可し、
# 外部バインドを拒否する（fail-closed）。
#
# 運用:
#   AICHAN_API_TOKEN=$(python -c 'import secrets;print(secrets.token_urlsafe(32))')
#   curl -H "Authorization: Bearer $AICHAN_API_TOKEN" http://localhost:8080/api/health

_LOCAL_ADDRS = frozenset({"127.0.0.1", "::1", "localhost"})


def _get_api_token() -> Optional[str]:
    """環境変数から API token を取得する。未設定なら None。"""
    token = os.environ.get("AICHAN_API_TOKEN", "").strip()
    return token if token else None


async def require_auth(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> None:
    """Bearer token 認証。token 未設定時は localhost のみ許可。

    - AICHAN_API_TOKEN 設定済み: `Authorization: Bearer <token>` 必須、
      `hmac.compare_digest` で定時間比較。
    - 未設定: リモート IP が localhost でなければ 401。
    """
    expected = _get_api_token()
    if expected is None:
        client_host = request.client.host if request.client else ""
        if client_host not in _LOCAL_ADDRS:
            logger.warning(
                "AICHAN_API_TOKEN 未設定で非 localhost からのアクセス: %s",
                client_host,
            )
            raise HTTPException(
                status_code=401,
                detail=(
                    "API token 未設定のため localhost のみ許可されています。"
                    "AICHAN_API_TOKEN 環境変数を設定してください。"
                ),
            )
        return

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token 必須")
    provided = authorization[len("Bearer "):].strip()
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="認証に失敗しました")

WEB_DIR = Path(__file__).parent
STATIC_DIR = WEB_DIR / "static"

# ── CORS 許可オリジン設定 ──────────────────────────────────────
# 環境変数 AICHAN_ALLOWED_ORIGINS でカスタマイズ可能
# デフォルト: ローカルホスト + 同一LAN iPhone のみ
_DEFAULT_ORIGINS = [
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:3000",
    "http://127.0.0.1",
    "http://127.0.0.1:8080",
]

def _get_allowed_origins() -> list[str]:
    """環境変数または設定から許可オリジンを取得する。"""
    env_origins = os.environ.get("AICHAN_ALLOWED_ORIGINS", "")
    if env_origins.strip() == "*":
        # 明示的にワイルドカードを指定した場合のみ許可（ローカル開発限定）
        logger.warning(
            "CORS ワイルドカード (*) が設定されています。本番環境では使用しないでください。"
        )
        return ["*"]
    if env_origins:
        return [o.strip() for o in env_origins.split(",") if o.strip()]
    return _DEFAULT_ORIGINS


# ── レート制限 ──────────────────────────────────────────────────
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded

    _limiter = Limiter(key_func=get_remote_address)
    _RATE_LIMIT_AVAILABLE = True
except ImportError:
    _limiter = None  # type: ignore[assignment]
    _RATE_LIMIT_AVAILABLE = False
    logger.debug("slowapi が利用できません。レート制限は無効です。")


# ── リクエスト/レスポンスモデル ──────────────────────────────


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    from_voice: bool = False  # 音声入力フラグ


class ChatResponse(BaseModel):
    reply: str
    emotion: dict
    mode: str = "family"


class GreetingResponse(BaseModel):
    greeting: str
    emotion: dict


class EmotionResponse(BaseModel):
    state: dict
    label: str
    emoji: str


class HealthResponse(BaseModel):
    status: str
    uptime: float
    llm_loaded: bool
    turn_count: int


# ── AiChan ラッパー ──────────────────────────────────────────


class AiChanWebBridge:
    """AiChan インスタンスをスレッドセーフにラップする。"""

    def __init__(self, base_dir: Path) -> None:
        self._lock = threading.Lock()
        self._start_time = time.time()
        self._ai: Optional[object] = None
        self._base_dir = base_dir

    def initialize(self) -> None:
        """AiChan を初期化する（同期、起動時に1回だけ呼ぶ）。"""
        from core.ai_chan import AiChan

        logger.info("AiChan 初期化中...")
        self._ai = AiChan(base_dir=self._base_dir)
        logger.info("AiChan 初期化完了 (LLM loaded: %s)", self._ai.llm_loaded)

    @property
    def ai(self):
        return self._ai

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time

    def chat(self, message: str, from_voice: bool = False) -> tuple[str, dict, str]:
        """スレッドセーフな chat 呼び出し。(reply, emotion_dict, mode) を返す。"""
        if self._ai is None:
            raise RuntimeError("AiChan not initialized")

        # 音声入力の場合、誤認識補正ヒントを付与して LLM に文脈推測させる
        if from_voice:
            actual_message = (
                f"[音声入力メモ: 音声認識の誤りがある可能性があります。"
                f"これまでの会話の流れや文脈から、ユーザーが本当に言おうとしていたことを推測して、"
                f"自然に返答してください。誤認識と思われる場合は「○○のことかな？」と確認しながら返してもOKです]\n"
                f"{message}"
            )
        else:
            actual_message = message

        with self._lock:
            reply = self._ai.chat(actual_message)
            emotion = self._get_emotion_dict()
            mode = "family"
            mm = getattr(self._ai, "mode_manager", None)
            if mm:
                mode = mm.current_mode
        return reply, emotion, mode

    def greeting(self, trigger: str = "chat_open") -> tuple[str, dict]:
        """スレッドセーフな挨拶生成。重い LLM 呼び出しを避け即応テキストを返す。"""
        if self._ai is None:
            raise RuntimeError("AiChan not initialized")
        import datetime
        hour = datetime.datetime.now().hour
        if hour < 11:
            quick = "おはよう！今日もよろしくね😊"
        elif hour < 17:
            quick = "こんにちは！何話す？😊"
        else:
            quick = "こんばんは！今日はどうだった？😊"
        # 感情だけロック内で取得（LLM は呼ばない）
        with self._lock:
            emotion = self._get_emotion_dict()
        return quick, emotion

    def get_emotion(self) -> tuple[dict, str, str]:
        """現在の感情状態を返す（スレッドセーフ）。"""
        if self._ai is None:
            return {}, "元気", "😊"
        with self._lock:
            emotion = self._get_emotion_dict()
            label = "元気"
            emoji = "😊"
            try:
                display = self._ai.emotion.get_display_string()
                # "😊 元気" のような形式をパース
                if display and len(display) >= 2:
                    emoji = display[0]
                    label = display[2:].strip() if len(display) > 2 else label
            except Exception:
                pass
        return emotion, label, emoji

    def _get_emotion_dict(self) -> dict:
        """感情状態を辞書で返す。"""
        try:
            return self._ai.emotion.state.to_dict()
        except Exception:
            return {}


# ── FastAPI アプリケーション ──────────────────────────────────


def create_app(base_dir: str | Path = ".") -> FastAPI:
    """FastAPI アプリケーションを作成する。"""
    base_path = Path(base_dir)
    bridge = AiChanWebBridge(base_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 起動時: AiChan を別スレッドで初期化（ブロッキング処理のため）
        await asyncio.to_thread(bridge.initialize)
        app.state.bridge = bridge
        logger.info("Web API 起動完了")
        yield
        logger.info("Web API シャットダウン")

    app = FastAPI(
        title="アイ Web API",
        description="アイとブラウザからおはなしできる API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # ── レート制限ミドルウェア ─────────────────────────────────
    if _RATE_LIMIT_AVAILABLE and _limiter is not None:
        app.state.limiter = _limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── CORS ─────────────────────────────────────────────────
    allowed_origins = _get_allowed_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
    )

    # ── エンドポイント ────────────────────────────────────

    @app.get("/api/health", response_model=HealthResponse)
    async def health(_auth: None = Depends(require_auth)):
        b = app.state.bridge
        ai = b.ai
        return HealthResponse(
            status="ok",
            uptime=b.uptime,
            llm_loaded=getattr(ai, "llm_loaded", False) if ai else False,
            turn_count=getattr(ai, "turn_count", 0) if ai else 0,
        )

    # chat エンドポイント: レート制限 30リクエスト/分
    if _RATE_LIMIT_AVAILABLE and _limiter is not None:
        @app.post("/api/chat", response_model=ChatResponse)
        @_limiter.limit("30/minute")
        async def chat(request: Request, req: ChatRequest, _auth: None = Depends(require_auth)):
            b = app.state.bridge
            if b.ai is None or not getattr(b.ai, "llm_loaded", False):
                raise HTTPException(503, "アイはまだ準備中です")
            try:
                reply, emotion, mode = await asyncio.to_thread(b.chat, req.message, req.from_voice)
                return ChatResponse(reply=reply, emotion=emotion, mode=mode)
            except Exception:
                logger.exception("chat error")
                raise HTTPException(500, "内部エラーが発生しました")
    else:
        @app.post("/api/chat", response_model=ChatResponse)
        async def chat(req: ChatRequest, _auth: None = Depends(require_auth)):  # type: ignore[misc]
            b = app.state.bridge
            if b.ai is None or not getattr(b.ai, "llm_loaded", False):
                raise HTTPException(503, "アイはまだ準備中です")
            try:
                reply, emotion, mode = await asyncio.to_thread(b.chat, req.message, req.from_voice)
                return ChatResponse(reply=reply, emotion=emotion, mode=mode)
            except Exception:
                logger.exception("chat error")
                raise HTTPException(500, "内部エラーが発生しました")

    @app.get("/api/greeting", response_model=GreetingResponse)
    async def greeting(trigger: str = "chat_open", _auth: None = Depends(require_auth)):
        b = app.state.bridge
        if b.ai is None or not getattr(b.ai, "llm_loaded", False):
            return GreetingResponse(greeting="もうちょっとだけ待ってね…", emotion={})
        try:
            text, emotion = await asyncio.to_thread(b.greeting, trigger)
            return GreetingResponse(greeting=text, emotion=emotion)
        except Exception:
            logger.exception("greeting error")
            return GreetingResponse(greeting="どうしたの？", emotion={})

    @app.get("/api/emotion", response_model=EmotionResponse)
    async def emotion(_auth: None = Depends(require_auth)):
        b = app.state.bridge
        state, label, emoji = b.get_emotion()
        return EmotionResponse(state=state, label=label, emoji=emoji)

    # akashic エンドポイント: レート制限 10リクエスト/分
    class AkashicRequest(BaseModel):
        text: str = Field(..., min_length=1, max_length=500)
        depth: int = Field(2, ge=1, le=5)

    class AkashicApiResponse(BaseModel):
        text: str
        depth: int
        phi_score: float
        field_resonances: dict
        akashic_available: bool
        error: Optional[str] = None

    if _RATE_LIMIT_AVAILABLE and _limiter is not None:
        @app.post("/api/akashic", response_model=AkashicApiResponse)
        @_limiter.limit("10/minute")
        async def akashic_endpoint(request: Request, req: AkashicRequest, _auth: None = Depends(require_auth)):
            return await _run_akashic(req.text, req.depth, AkashicApiResponse)
    else:
        @app.post("/api/akashic", response_model=AkashicApiResponse)
        async def akashic_endpoint(req: AkashicRequest, _auth: None = Depends(require_auth)):  # type: ignore[misc]
            return await _run_akashic(req.text, req.depth, AkashicApiResponse)

    async def _run_akashic(text: str, depth: int, ResponseModel) -> object:
        """アカシックコア処理の共通実装。"""
        try:
            from core.akashic.unified_field import UnifiedField
            field = UnifiedField()
            sig = await asyncio.to_thread(field.resonate, text)
            return ResponseModel(
                text=text,
                depth=depth,
                phi_score=sig.phi_score,
                field_resonances=dict(sig.resonances),
                akashic_available=True,
            )
        except Exception as e:
            logger.debug("akashic endpoint error: %s", e)
            return ResponseModel(
                text=text,
                depth=depth,
                phi_score=0.0,
                field_resonances={},
                akashic_available=False,
                error="アカシックコアは現在利用できません",
            )

    # ── 静的ファイル & フロントエンド ─────────────────────

    @app.get("/")
    async def index():
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path, media_type="text/html")
        return HTMLResponse("<h1>アイ Web API</h1><p>static/index.html が見つかりません</p>")

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app
