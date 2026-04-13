"""
ファイル学習エンジン（機能③）
PDF・テキスト・Markdown ファイルを読み込んで Phi-3 で要約・学習します。
完全ローカル動作。

PDF 対応には PyMuPDF が必要: pip install pymupdf
テキスト・Markdown・CSV は追加インストール不要。
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from datetime import datetime

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

# サポートする拡張子
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown", ".csv", ".log", ".py", ".json"}


def is_file_path(text: str) -> Path | None:
    """
    テキストからファイルパスっぽい文字列を抽出して Path を返す。
    実際にファイルが存在する場合のみ返す。
    """
    # /path/to/file や ~/path 形式
    m = re.search(r'(?:^|[\s「」])(/[^\s　]+|~/[^\s　]+)', text)
    if not m:
        return None
    raw = m.group(1).strip().rstrip("。、」）")
    p = Path(raw).expanduser()
    if p.exists() and p.is_file():
        return p
    return None


class FileLearner:
    """
    ファイル学習エンジン。
    - read_file(): ファイルからテキストを抽出
    - store(): learning/ に JSONL として保存
    """

    def __init__(self, data_dir: Path, learning_dir: Path):
        self.data_dir     = Path(data_dir)
        self.learning_dir = Path(learning_dir)
        self.learning_dir.mkdir(parents=True, exist_ok=True)
        self._log_path    = self.learning_dir / "file_learned.jsonl"

    # ─── テキスト抽出 ────────────────────────────────────────────

    def read_file(self, path: Path) -> dict:
        """
        ファイルを読み込んでテキストを返す。
        戻り値:
          成功: {"path", "name", "text", "ext"}
          失敗: {"error": "..."}
        """
        path = Path(path)
        ext  = path.suffix.lower()

        if ext not in SUPPORTED_EXTENSIONS:
            return {
                "error": (
                    f"このファイル形式（{ext}）は対応してないよ。\n"
                    f"対応: {', '.join(SUPPORTED_EXTENSIONS)}"
                )
            }

        if not path.exists():
            return {"error": f"ファイルが見つからないよ: {path}"}

        try:
            if ext == ".pdf":
                text = self._read_pdf(path)
            else:
                text = path.read_text(encoding="utf-8", errors="ignore")

            if not text.strip():
                return {"error": "ファイルが空か、テキストを取り出せなかったよ。"}

            return {
                "path": str(path),
                "name": path.name,
                "text": text,
                "ext":  ext,
                "size_chars": len(text),
            }

        except Exception as e:
            return {"error": f"読み込みエラー: {e}"}

    def _read_pdf(self, path: Path) -> str:
        """PDF からテキストを抽出する"""
        if not PYMUPDF_AVAILABLE:
            raise RuntimeError(
                "PDF 読み込みには PyMuPDF が必要です。\n"
                "pip install pymupdf でインストールしてね。"
            )
        doc  = fitz.open(str(path))
        pages = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        return "\n".join(pages)

    # ─── 要約・保存 ──────────────────────────────────────────────

    def summarize_with_llm(self, data: dict, llm_engine) -> str:
        """Phi-3 でファイル内容を要約する（完全ローカル）"""
        name    = data.get("name", "ファイル")
        snippet = data.get("text", "")[:1500]

        prompt_text = (
            f"ファイル名「{name}」の内容の一部：\n{snippet}\n\n"
            "この内容を日本語で2〜3文にまとめて。"
        )
        try:
            messages = [
                {"role": "system", "content": "日本語で簡潔に要約してください。"},
                {"role": "user",   "content": prompt_text},
            ]
            result = llm_engine.generate_chat(messages)
            return result.strip() if result.strip() else snippet[:200]
        except Exception:
            return snippet[:200]

    def store(self, data: dict, summary: str) -> bool:
        """学習データとして保存"""
        entry = {
            "path":       data["path"],
            "name":       data["name"],
            "user":       f"{data['name']}の内容を教えて",
            "ai":         summary,
            "text_snippet": data.get("text", "")[:400],
            "learned_at": datetime.now().isoformat()[:16],
        }
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True

    def list_learned(self) -> list[dict]:
        if not self._log_path.exists():
            return []
        results = []
        for line in self._log_path.read_text("utf-8").splitlines():
            if line.strip():
                try:
                    results.append(json.loads(line))
                except Exception:
                    pass
        return results

    @staticmethod
    def supported_extensions() -> str:
        return ", ".join(sorted(SUPPORTED_EXTENSIONS))
