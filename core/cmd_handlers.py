"""
コマンドハンドラ
CMD_* パターンの定義と、ユーザー入力のコマンドマッチング・実行を担当します。
"""
from __future__ import annotations

import re
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.ai_chan import AiChan

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# 特殊コマンドのパターン（モジュールレベル定数）
# ──────────────────────────────────────────────────────────────

CMD_REMEMBER   = re.compile(r"^(これを覚えて|覚えて)[：:。]?\s*(.+)$", re.DOTALL)
CMD_FORGET     = re.compile(r"^(これを忘れて|忘れて)[：:。]?\s*(.+)$", re.DOTALL)
CMD_IMPORTANT  = re.compile(r"^(大切な思い出|絶対に覚えて)[：:。]?\s*(.+)$", re.DOTALL)
CMD_MEMORY     = re.compile(r"^(記憶|思い出)を?(見せて|確認|教えて)$")
CMD_PROFILE    = re.compile(r'^私の(.+)は[\u300c\u201c]?(.+?)[\u300d\u201d]?だよ$')
CMD_SEARCH     = re.compile(r'^(記憶を?検索|思い出を?探して)[：:]\s*(.+)$')
CMD_DIARY      = re.compile(r'^(日記|今日の日記)(を?(書いて|見せて|読んで))?$')
CMD_ANNIV_ADD  = re.compile(r'^(記念日|誕生日)を?登録[：:]\s*(.+?)\s+(\d{1,2})月(\d{1,2})日$')
CMD_ANNIV_LIST = re.compile(r'^(記念日|誕生日)(一覧|リスト|を?見せて)$')
CMD_YT_LIST    = re.compile(r'^(YouTube|ユーチューブ).*(学習|覚えた|見た).*$')
CMD_WEB_LIST   = re.compile(r'^(Web|ウェブ|サイト|ホームページ).*(学習|覚えた|読んだ).*$')
CMD_FILE_LIST  = re.compile(r'^(ファイル|PDF|書類).*(学習|覚えた|読んだ).*$')
CMD_CALENDAR   = re.compile(r'^(カレンダー|予定|スケジュール).*(見せて|確認|教えて|ある)?.*$')
CMD_BATTERY    = re.compile(r'^(バッテリー|充電|電池).*(残量|どのくらい|教えて|確認|何)?.*$')
CMD_AUTO_LEARN = re.compile(r'^(自動学習|学習スケジュール).*(状況|設定|見せて|確認|追加|登録|今すぐ|実行)?.*$')
CMD_LEARN_ADD  = re.compile(r'^(学習先|学習ソース)を?(追加|登録)[：:]\s*(.+)$')
CMD_LEARN_NOW  = re.compile(r'^(今すぐ|すぐに|即座に)?(自動)?学習(して|実行|開始)$')
CMD_MEMO_ADD   = re.compile(r'^(学習メモ|メモ)を?(覚えて|登録|追加)[：:。]?\s*(.+)$', re.DOTALL)
CMD_MEMO_LIST  = re.compile(r'^(学習メモ|メモ)(一覧|リスト|を?見せて|確認)$')
CMD_PROPOSAL   = re.compile(r'^(提案|改善案|自己開発)(一覧|リスト|を?見せて|確認|分析|実行)?$')
CMD_PROPOSAL_OK = re.compile(r'^(提案|改善案)を?(承認|OK|おっけ)[：:。]?\s*(.+)$')
CMD_PROPOSAL_NO = re.compile(r'^(提案|改善案)を?(却下|NG|だめ)[：:。]?\s*(.+)$')
CMD_SELF_AWARE = re.compile(r'^(自分|自己)(認識|構造|分析|について).*$')
CMD_MINUTES    = re.compile(r'^(議事録)(一覧|リスト|を?見せて|確認|開いて)?$')

# Sprint 2.1: セキュリティコマンド
CMD_SECURITY   = re.compile(r'^(セキュリティ|防御|ガーディアン).*(チェック|確認|状態|スコア|診断).*$')
CMD_BACKUP     = re.compile(r'^(バックアップ).*(作成|実行|取って|して|一覧|リスト).*$')
CMD_LOCKDOWN   = re.compile(r'^(ロックダウン|緊急停止|キルスイッチ)(.*)$')
CMD_UNLOCK     = re.compile(r'^(ロック解除|アイ解除)$')

# Sprint J: サーバーホーム + 自律行動コマンド
CMD_SERVER_STATUS  = re.compile(r'^(サーバー|ホーム|家)(の?)?(状態|状況|確認|接続|ステータス).*$')
CMD_SERVER_DOCKER  = re.compile(r'^(サーバー|ホーム)(の?)?Docker(一覧|状態|コンテナ).*$')
CMD_SERVER_SYNC    = re.compile(r'^(サーバー|ホーム)(に?同期|と同期|同期して).*$')
CMD_SERVER_SETUP   = re.compile(r'^(サーバー|ホーム).*?(設定|登録|接続設定).*$')
CMD_PROACTIVE      = re.compile(r'^(話しかけて|会話して|何か話して).*$')

# Sprint K: 国産AI進化コマンド
CMD_KNOWLEDGE      = re.compile(r'^(知識|ナレッジ|知ってること)(グラフ|一覧|を?見せて|確認|について).*$')
CMD_RELATIONSHIP   = re.compile(r'^(関係性|親密度|仲良し度|絆)(を?見せて|確認|どのくらい).*$')
CMD_GROWTH         = re.compile(r'^(成長|進化|アイの成長)(レポート|状況|を?見せて|確認)?.*$')
CMD_QUALITY        = re.compile(r'^(品質|応答品質|会話品質)(レポート|スコア|を?見せて|確認)?.*$')

# ヤマト計画: 国産AI進化コマンド
CMD_YAMATO_DASH    = re.compile(r'^(ヤマト|アーキテクチャ|7層|七層)(ダッシュボード|状態|確認|を?見せて)?.*$')
CMD_MOE_STATUS     = re.compile(r'^(MoE|専門家|モデル切替|エキスパート)(状態|一覧|確認|を?見せて)?.*$')
CMD_LEARNING_STATUS = re.compile(r'^(継続学習|学習エンジン|学習状況)(状態|確認|を?見せて)?.*$')
CMD_SYNTH_GEN      = re.compile(r'^(合成データ|データ生成|学習データ)(生成|作成|を?見せて|状態)?.*$')
CMD_VERIFY_STATUS  = re.compile(r'^(検証|マルチエージェント|品質検証)(状態|結果|を?見せて|確認)?.*$')

# Sprint 3.0-A: マルチモーダルコマンド
CMD_SCREENSHOT  = re.compile(r'^(スクリーンショット|画面|スクショ)(を?見て|解析|を?教えて|チェック)')
CMD_CLIPBOARD_IMG = re.compile(r'^(クリップボード|貼り付け)(の?画像|を?見て|解析)')
CMD_IMAGE_ANALYZE = re.compile(r'^(この?画像|写真)(を?見て|解析|を?教えて|について)')

# Sprint 3.0-E: 防御進化コマンド
CMD_NETWORK_CHECK  = re.compile(r'^(ネットワーク|通信)(チェック|確認|を?見て|状態)')
CMD_PROCESS_CHECK  = re.compile(r'^(プロセス|アプリ)(チェック|確認|を?見て|状態)')
CMD_DEFENSE_REPORT = re.compile(r'^(防御|セキュリティ)(レポート|報告|ダッシュボード|全体)')

# Sprint 3.0: 生活アシスタント + 知識コマンド
CMD_TASK_ADD   = re.compile(r'^(タスク|やること|TODO)を?(追加|登録)[：:。]?\s*(.+)$', re.DOTALL)
CMD_TASK_DONE  = re.compile(r'^(タスク|やること).*(完了|終わった|できた).*(#?(\d+)).*$')
CMD_TASK_LIST  = re.compile(r'^(タスク|やること|TODO)(一覧|リスト|を?見せて|確認)?$')
CMD_HABIT_ADD  = re.compile(r'^(習慣)を?(追加|登録)[：:。]?\s*(.+)$')
CMD_HABIT_REC  = re.compile(r'^(.+?)(した|やった|できた|完了)！?$')
CMD_HABIT_LIST = re.compile(r'^(習慣)(一覧|リスト|を?見せて|確認|レポート)?$')
CMD_DOC_ADD    = re.compile(r'^(ドキュメント|資料|ファイル)を?(読んで|学習|追加)[：:。]?\s*(.+)$')
CMD_DOC_LIST   = re.compile(r'^(ドキュメント|資料)(一覧|リスト|を?見せて)$')
CMD_DOC_SEARCH = re.compile(r'^(資料|ドキュメント).*?(検索|探して)[：:。]?\s*(.+)$')

# ─── Web検索 コマンド ──────────────────
CMD_WEB_SEARCH   = re.compile(r'^(.+?)(について|を)?(調べて|検索|検索して|サーチ|ググって)$')
CMD_WEB_SEARCH_PREFIX = re.compile(r'^(検索|調べて|ググって|サーチ)[：:。]?\s*(.+)$')
CMD_WEB_FETCH    = re.compile(r'^(URL|サイト|ページ)(を?)?(読んで|取得|見て)[：:。]?\s*(.+)$')

# ─── コードエンジン コマンド（自然言語） ──────────────────
CMD_CODE_ANALYZE = re.compile(r'^(この)?コード(を?)?(見て|解析|分析|チェック|確認)[：:。]?\s*(.+)$', re.DOTALL)
CMD_CODE_REVIEW  = re.compile(r'^(この)?コード(を?)?(レビュー|レビューして|審査)[：:。]?\s*(.+)$', re.DOTALL)
CMD_CODE_FIX     = re.compile(r'^(この)?(エラー|バグ)(を?)?(直して|修正|修正して|フィックス)[：:。]?\s*(.+)$', re.DOTALL)
CMD_CODE_TEST    = re.compile(r'^(この)?コード(の?)?(テスト|テスト書いて|テスト作って|テスト生成)[：:。]?\s*(.+)$', re.DOTALL)
CMD_CODE_EXPLAIN = re.compile(r'^(この)?コード(を?)?(説明|説明して|教えて|解説)[：:。]?\s*(.+)$', re.DOTALL)
CMD_CODE_FILE    = re.compile(r'^(ファイル)(を?)?(見て|解析|レビュー|チェック)[：:。]?\s*(.+)$', re.DOTALL)
CMD_CODE_RUN     = re.compile(r'^(この)?コード(を?)?(実行|走らせて|動かして|実行して|ラン)[：:。]?\s*(.+)$', re.DOTALL)

# ─── コードエンジン スラッシュコマンド（E-01） ──────────────
# 書式: /code [analyze|review|fix|run|test|explain] <コード or パス>
CMD_SLASH_CODE    = re.compile(r'^/code(?:\s+(analyze|review|fix|run|test|explain))?\s+(.+)$', re.DOTALL | re.IGNORECASE)
CMD_SLASH_REVIEW  = re.compile(r'^/review\s+(.+)$', re.DOTALL)
CMD_SLASH_FIX     = re.compile(r'^/fix\s+(.+)$', re.DOTALL)
CMD_SLASH_RUN     = re.compile(r'^/run\s+(.+)$', re.DOTALL)
CMD_SLASH_EXPLAIN = re.compile(r'^/explain\s+(.+)$', re.DOTALL)
CMD_SLASH_TEST    = re.compile(r'^/test\s+(.+)$', re.DOTALL)
CMD_SLASH_CODE_HELP = re.compile(r'^/code\s*$')

# ─── ドキュメント出力 コマンド ──────────────────
CMD_EXPORT_WORD  = re.compile(r'^(Word|ワード|レポート|報告書)に?(まとめて|作って|出力|書いて|変換)[：:。]?\s*(.+)$', re.DOTALL)
CMD_EXPORT_PPTX  = re.compile(r'^(パワポ|PowerPoint|スライド|プレゼン)に?(まとめて|作って|出力|変換)[：:。]?\s*(.+)$', re.DOTALL)
CMD_EXPORT_EXCEL = re.compile(r'^(エクセル|Excel|表|一覧表|スプレッドシート)に?(まとめて|作って|出力|変換)[：:。]?\s*(.+)$', re.DOTALL)
CMD_EXPORT_AUTO  = re.compile(r'^(資料|ドキュメント|ファイル)に?(まとめて|出力して|書き出して)[：:。]?\s*(.+)$', re.DOTALL)

# ─── モード切替コマンド ──────────────────────────────
CMD_MODE_SWITCH   = re.compile(r'^(?:モード切替|モードチェンジ)\s+(.+)$')
CMD_MODE_STATUS   = re.compile(r'^(?:モード|モード確認|現在のモード)$')
CMD_MODE_FAMILY   = re.compile(r'^(?:家族モード|ファミリーモード|いつものモード)$')
CMD_MODE_AGENT    = re.compile(r'^(?:お仕事モード|エージェントモード|作業モード)$')
CMD_MODE_LEARN    = re.compile(r'^(?:学習モード|勉強モード|お勉強モード)$')
CMD_MODE_CREATIVE = re.compile(r'^(?:創作モード|クリエイティブモード)$')

# ─── データエクスポート コマンド ──────────────────────
CMD_DATA_EXPORT = re.compile(r'^(?:データエクスポート|データ出力|エクスポート)\s*(.*)$')

# ─── パーソナリティカード コマンド ────────────────────
CMD_PERSONALITY_CARD = re.compile(r'^(?:パーソナリティ|性格カード|自己紹介カード)$')

# ─── ユーザープロファイル コマンド ────────────────────
CMD_USER_PROFILE = re.compile(r'^(?:ユーザー登録|プロファイル登録)\s+(.+)$')
CMD_USER_SWITCH  = re.compile(r'^(?:ユーザー切替|ユーザー変更)\s+(.+)$')
CMD_USER_LIST    = re.compile(r'^(?:ユーザー一覧|ユーザーリスト)$')

# ─── 声紋認証 コマンド ──────────────────────────────
CMD_VOICE_REGISTER = re.compile(r'^(?:声紋登録|声を登録|声を覚えて|ボイス登録)\s*(.*)$')
CMD_VOICE_IDENTIFY = re.compile(r'^(?:声紋認証|声で認証|声で確認|ボイス認証)$')
CMD_VOICE_STATUS   = re.compile(r'^(?:声紋|ボイスID|声紋状態|声の登録)(?:状態|確認|を?見せて)?$')

# ─── 音声管理 コマンド ──────────────────────────────
CMD_VOICE_INFO    = re.compile(r'^(?:音声確認|音声状態|音声設定|/voice\s*$)')
CMD_VOICE_SWITCH  = re.compile(r'^(?:音声切替|音声変更|/voice\s+switch)\s*(.*)$')
CMD_VOICE_TEST    = re.compile(r'^(?:音声テスト|声を?テスト|/voice\s+test)\s*(.*)$')
CMD_VOICE_LIST    = re.compile(r'^(?:音声一覧|音声リスト|/voice\s+list)$')

# ─── イントネーション学習 コマンド ────────────────────
CMD_PROSODY_LEARN  = re.compile(r'^(?:イントネーション学習|声を?学習|抑揚学習|話し方を?学習|話し方を?覚えて)$')
CMD_PROSODY_FILE   = re.compile(r'^(?:イントネーション学習|声を?学習)\s+(.+)$')
CMD_PROSODY_STATUS = re.compile(r'^(?:イントネーション|抑揚|話し方)(の?状態|確認|を?見せて)$')
CMD_PROSODY_APPLY  = re.compile(r'^(?:イントネーション|抑揚|話し方)(を?適用|反映|オン)$')
CMD_PROSODY_RESET  = re.compile(r'^(?:イントネーション|抑揚|話し方)(を?リセット|初期化|オフ)$')

# ─── ヘルスチェック コマンド ──────────────────────────
CMD_HEALTH = re.compile(r'^(?:ヘルスチェック|健康診断|システム診断|診断)$')

# ─── Sprint 1: リサーチ / 画像生成 / タスク コマンド ──────────
CMD_RESEARCH = re.compile(r'^(.+)(を?)(調べて|検索して|リサーチして|調査して|教えて)$')
CMD_IMAGE    = re.compile(r'^(.+)(の?)画像(を?)(作って|生成して|描いて|作成して)$')
CMD_TASK     = re.compile(r'^(.+)(を?)(やって|進めて|実行して|作って|まとめて)(ください|くれる|くれ)?$')

# ─── Sprint 2: WebBuilder / CodeReviewer / DocAgent コマンド ───
CMD_WEB_BUILD   = re.compile(
    r'^(.+)(の?)?(HP|ホームページ|サイト|ウェブサイト|ウェブ)(を?)?(作って|作成して|構成して)$'
)
CMD_CODE_REVIEW_S2 = re.compile(
    r'^(このコード|コード)(を?)?(レビュー|見て|チェック|確認)(して|くれ|ください)?$'
)
CMD_DOC_CREATE  = re.compile(
    r'^(.+)(の?)?(提案書|企画書|報告書|書類|資料|メール)(を?)?(作って|書いて|作成して)$'
)


# ──────────────────────────────────────────────────────────────
# コマンドハンドラクラス
# ──────────────────────────────────────────────────────────────

class CommandHandler:
    """
    ユーザー入力を CMD_* パターンで照合し、マッチしたら
    対応するハンドラを実行して応答文を返す。
    マッチしなければ None を返す。
    """

    def __init__(self, ai: AiChan) -> None:
        self.ai = ai

    # ─── 公開インターフェース ──────────────────────────

    def try_handle(self, user_input: str) -> str | None:
        """
        user_input がコマンドにマッチすれば応答文字列を返す。
        マッチしなければ None を返す。
        """
        return self._dispatch(user_input)

    # ─── ディスパッチ ─────────────────────────────────

    def _dispatch(self, user_input: str) -> str | None:  # noqa: C901
        """全コマンドパターンを順に照合する"""
        ai = self.ai

        # モード切替コマンド
        mode_result = self._handle_mode(user_input)
        if mode_result is not None:
            return mode_result

        # 声紋認証コマンド
        voice_result = self._handle_voice_id(user_input)
        if voice_result is not None:
            return voice_result

        # 音声管理コマンド
        voice_mgmt_result = self._handle_voice_management(user_input)
        if voice_mgmt_result is not None:
            return voice_mgmt_result

        # イントネーション学習コマンド
        prosody_result = self._handle_prosody_learning(user_input)
        if prosody_result is not None:
            return prosody_result

        # 「これを覚えて: ○○」
        m = CMD_REMEMBER.match(user_input)
        if m:
            content = m.group(2).strip()
            ai.memory.remember(content, is_important=False)
            return f"うん、「{content}」を覚えたよ！大切にしておくね。\U0001f495"

        # 「絶対に覚えて: ○○」（保護記憶）
        m = CMD_IMPORTANT.match(user_input)
        if m:
            content = m.group(2).strip()
            ai.memory.remember(content, is_important=True)
            return f"「{content}」を大切な思い出として、ずっと覚えておくね。絶対に忘れないよ！\u2728"

        # 「これを忘れて: ○○」
        m = CMD_FORGET.match(user_input)
        if m:
            content = m.group(2).strip()
            deleted = ai.memory.forget(content)
            if deleted > 0:
                return f"「{content}」に関する記憶を {deleted} 件削除したよ。"
            return f"「{content}」に関する記憶は見つからなかったよ。（保護された思い出は削除できないんだ）"

        # 「記憶を見せて」
        if CMD_MEMORY.match(user_input):
            return ai._show_memory_summary()

        # 「私の○○は△△だよ」（プロファイル登録）
        m = CMD_PROFILE.match(user_input)
        if m:
            key = m.group(1).strip()
            value = m.group(2).strip()
            ai.memory.set_user_profile(key, value)
            return f"了解！あなたの「{key}」は「{value}」だね。ちゃんと覚えたよ\U0001f60a"

        # 「記憶を検索: ○○」
        m = CMD_SEARCH.match(user_input)
        if m:
            query = m.group(2).strip()
            all_mems = ai.memory.get_recent(limit=200)
            if ai.semantic_search.is_ready():
                results = ai.semantic_search.search(query, all_mems, limit=5)
            else:
                results = ai.memory.search(query, limit=5)
            if not results:
                return f"「{query}」に関する記憶は見つからなかったよ。"
            lines = [f"「{query}」に関する記憶だよ："]
            for r in results:
                snippet = r.content[:60].replace("\n", " ")
                lines.append(f"・{snippet}…")
            return "\n".join(lines)

        # 「日記を見せて」「日記を書いて」
        if CMD_DIARY.match(user_input):
            return self._handle_diary(user_input)

        # 「記念日を登録: 名前 M月D日」
        m = CMD_ANNIV_ADD.match(user_input)
        if m:
            is_bday = m.group(1) == "誕生日"
            label = m.group(2).strip()
            month = int(m.group(3))
            day = int(m.group(4))
            ai.anniversary.add(label, month, day, is_birthday=is_bday)
            kind = "誕生日" if is_bday else "記念日"
            return f"「{label}」を{kind}として{month}月{day}日に登録したよ！毎年その日になったら話しかけるね。"

        # 「記念日一覧」
        if CMD_ANNIV_LIST.match(user_input):
            items = ai.anniversary.list_all()
            if not items:
                return "まだ記念日は登録されていないよ。「誕生日を登録: 名前 M月D日」で追加できるよ！"
            lines = ["登録済みの記念日だよ："]
            for item in items:
                kind = "\U0001f382" if item.get("is_birthday") else "\U0001f389"
                lines.append(f"{kind} {item['label']}  {item['month']}月{item['day']}日")
            return "\n".join(lines)

        # 「YouTube学習一覧」
        if CMD_YT_LIST.match(user_input):
            return ai._show_youtube_learned()

        # 「Web学習一覧」
        if CMD_WEB_LIST.match(user_input):
            learned = ai.web_learner.list_learned()
            if not learned:
                return "まだ Web ページを学習してないよ。URL をチャットに貼ると学習できるよ！"
            lines = [f"学習済み Web ページ {len(learned)} 件だよ："]
            for item in learned[-8:]:
                lines.append(f"・「{item['title']}」（{item.get('learned_at', '')[:10]}）")
            return "\n".join(lines)

        # 「ファイル学習一覧」
        if CMD_FILE_LIST.match(user_input):
            learned = ai.file_learner.list_learned()
            if not learned:
                return "まだファイルを学習してないよ。ファイルのパスをチャットに貼ると学習できるよ！"
            lines = [f"学習済みファイル {len(learned)} 件だよ："]
            for item in learned[-8:]:
                lines.append(f"・「{item['name']}」（{item.get('learned_at', '')[:10]}）")
            return "\n".join(lines)

        # 「カレンダーを見せて」
        if CMD_CALENDAR.match(user_input):
            from core.calendar_reader import format_events_for_chat
            return format_events_for_chat()

        # 「バッテリー残量」
        if CMD_BATTERY.match(user_input):
            from core.battery_monitor import get_battery_info
            info = get_battery_info()
            if not info["found"]:
                return "バッテリー情報を取得できなかったよ。"
            pct = info["percent"]
            charging = "充電中" if info["charging"] else "放電中"
            return f"バッテリーは今 {pct}%（{charging}）だよ。"

        # YouTube URL が含まれていたら学習処理
        from core.youtube_learner import extract_youtube_url
        yt_url = extract_youtube_url(user_input)
        if yt_url:
            return ai._learn_youtube(yt_url)

        # Web URL が含まれていたら学習処理
        from core.web_learner import is_web_url
        web_url = is_web_url(user_input)
        if web_url:
            return ai._learn_web(web_url)

        # ファイルパスが含まれていたら学習処理
        from core.file_learner import is_file_path
        file_path = is_file_path(user_input)
        if file_path:
            return ai._learn_file(file_path)

        # 自動学習スケジュール確認・管理
        if CMD_AUTO_LEARN.match(user_input):
            return ai._show_auto_learn_status()

        # 学習ソース追加
        m = CMD_LEARN_ADD.match(user_input)
        if m:
            value = m.group(3).strip()
            return ai._add_learn_source(value)

        # 即時学習実行
        if CMD_LEARN_NOW.match(user_input):
            return ai._run_auto_learn_now()

        # メモ登録
        m = CMD_MEMO_ADD.match(user_input)
        if m:
            text = m.group(3).strip()
            ai.auto_learner.add_memo(text)
            return f"メモを学習リストに登録したよ！\U0001f4dd\n「{text[:60]}」\n夜の復習タイムに振り返るね。"

        # メモ一覧
        if CMD_MEMO_LIST.match(user_input):
            return ai._show_memo_list()

        # ─── 自己開発コマンド ──────────────────────────────

        if CMD_PROPOSAL.match(user_input):
            return ai._handle_proposal_command(user_input)

        m = CMD_PROPOSAL_OK.match(user_input)
        if m:
            pid = m.group(3).strip()
            sd = getattr(ai, "self_dev", None)
            if sd and sd.proposal_store.approve(pid):
                return f"提案「{pid}」を承認したよ！対応を進めるね。"
            return f"提案「{pid}」が見つからなかったよ。「提案一覧」で確認してみてね。"

        m = CMD_PROPOSAL_NO.match(user_input)
        if m:
            pid = m.group(3).strip()
            sd = getattr(ai, "self_dev", None)
            if sd and sd.proposal_store.reject(pid):
                return f"提案「{pid}」を却下したよ。了解！"
            return f"提案「{pid}」が見つからなかったよ。"

        if CMD_SELF_AWARE.match(user_input):
            return ai._show_self_awareness()

        if CMD_MINUTES.match(user_input):
            return ai._show_minutes_list()

        # ─── Sprint 3.0-A: マルチモーダルコマンド ────────────────

        if CMD_SCREENSHOT.match(user_input) and getattr(ai, "multimodal", None):
            # B5 fix (2026-04-21): screenshot は明示同意なしには撮らない
            _auto = (getattr(ai, "settings", {}) or {}).get("autonomous", {})
            if not _auto.get("screenshot_enabled", False):
                return (
                    "スクリーンショット機能は OFF になってるよ。"
                    "設定ウィンドウ → プライバシーで同意して有効化してね。"
                )
            return ai.multimodal.describe_screenshot()

        if CMD_CLIPBOARD_IMG.match(user_input) and getattr(ai, "multimodal", None):
            _auto = (getattr(ai, "settings", {}) or {}).get("autonomous", {})
            if not _auto.get("clipboard_watch", False):
                return (
                    "クリップボードのぞき見は OFF になってるよ。"
                    "設定ウィンドウ → プライバシーで同意してね。"
                )
            return ai.multimodal.describe_clipboard_image()

        if CMD_IMAGE_ANALYZE.match(user_input) and getattr(ai, "multimodal", None):
            return (
                "画像パスを教えてね！「資料を読んで: /path/to/image.png」の形式で送ってね。\n"
                "または「スクショ見て」「クリップボードの画像を見て」も使えるよ！"
            )

        # ─── Sprint 3.0-E: 防御進化コマンド ────────────────────

        if CMD_NETWORK_CHECK.match(user_input):
            if getattr(ai, "network_monitor", None):
                return ai.network_monitor.get_connection_summary()
            return "ネットワークモニターが初期化されていないよ。"

        if CMD_PROCESS_CHECK.match(user_input):
            if getattr(ai, "process_monitor", None):
                return ai.process_monitor.get_summary()
            return "プロセスモニターが初期化されていないよ。"

        if CMD_DEFENSE_REPORT.match(user_input):
            if getattr(ai, "defense_dashboard", None):
                return ai.defense_dashboard.get_full_report()
            return "防御ダッシュボードが初期化されていないよ。"

        # ─── Sprint 3.0: 生活アシスタント + 知識コマンド ────────

        m = CMD_TASK_ADD.match(user_input)
        if m and getattr(ai, "task_manager", None):
            text = m.group(3).strip()
            task = ai.task_manager.add_from_text(text)
            due = f"（期限: {task.due_date}）" if task.due_date else ""
            return f"\U0001f4cc タスクを登録したよ！\n「{task.title}」{due}\nID: #{task.id}"

        m = CMD_TASK_DONE.match(user_input)
        if m and getattr(ai, "task_manager", None):
            task_id = int(m.group(4))
            if ai.task_manager.complete(task_id):
                return f"\u2705 タスク #{task_id} を完了にしたよ！お疲れさま！"
            return f"タスク #{task_id} が見つからないよ。"

        if CMD_TASK_LIST.match(user_input) and getattr(ai, "task_manager", None):
            return ai.task_manager.format_task_list()

        m = CMD_HABIT_ADD.match(user_input)
        if m and getattr(ai, "habit_tracker", None):
            name = m.group(3).strip()
            ai.habit_tracker.add_habit(name)
            return f"\U0001f3af 習慣「{name}」を登録したよ！毎日一緒に頑張ろうね。"

        if CMD_HABIT_LIST.match(user_input) and getattr(ai, "habit_tracker", None):
            if "レポート" in user_input:
                return ai.habit_tracker.get_weekly_report()
            return ai.habit_tracker.get_today_status()

        m = CMD_HABIT_REC.match(user_input)
        if m and getattr(ai, "habit_tracker", None):
            name = m.group(1).strip()
            if name in ai.habit_tracker.list_habits():
                ai.habit_tracker.record(name)
                streak = ai.habit_tracker.get_streak(name)
                msg = f"\u2705 「{name}」を記録したよ！"
                if streak > 1:
                    msg += f" \U0001f525 {streak}日連続！すごい！"
                return msg

        m = CMD_DOC_ADD.match(user_input)
        if m and getattr(ai, "rag", None):
            path = m.group(3).strip()
            result = ai.rag.add_document(path)
            if "error" in result:
                return f"読み込めなかったよ: {result['error']}"
            if result.get("status") == "already_indexed":
                return "この資料はもう読み込み済みだよ！"
            return f"\U0001f4c4 「{result['name']}」を読み込んだよ！{result['chunks']}チャンクに分割して覚えたよ。"

        if CMD_DOC_LIST.match(user_input) and getattr(ai, "rag", None):
            docs = ai.rag.list_documents()
            if not docs:
                return "まだ資料は登録されていないよ。「資料を読んで: /path」で追加できるよ！"
            lines = ["\U0001f4da 登録済み資料："]
            for d in docs:
                lines.append(f"  \u2022 {d['name']} ({d['chunks']}チャンク)")
            return "\n".join(lines)

        m = CMD_DOC_SEARCH.match(user_input)
        if m and getattr(ai, "rag", None):
            query = m.group(3).strip()
            results = ai.rag.search(query, limit=3)
            if not results:
                return f"「{query}」に関する情報は資料から見つからなかったよ。"
            lines = [f"\U0001f4d6 「{query}」の検索結果："]
            for r in results:
                snippet = r["text"][:100].replace("\n", " ")
                lines.append(f"  [{r['doc_name']}] {snippet}…")
            return "\n".join(lines)

        # ─── Web検索 コマンド ──────────────────

        m = CMD_WEB_SEARCH.match(user_input)
        if m:
            return ai._handle_web_search(m.group(1).strip())

        m = CMD_WEB_SEARCH_PREFIX.match(user_input)
        if m:
            return ai._handle_web_search(m.group(2).strip())

        m = CMD_WEB_FETCH.match(user_input)
        if m:
            return ai._handle_web_fetch(m.group(4).strip())

        # ─── コードエンジン スラッシュコマンド（E-01） ──────────────

        m = CMD_SLASH_CODE_HELP.match(user_input)
        if m:
            return (
                "💻 コードエンジン コマンド一覧:\n"
                "  /code analyze <コード>  — 構造・品質分析\n"
                "  /code review <コード>   — レビュー（問題点指摘）\n"
                "  /code fix <エラー内容>  — バグ修正提案\n"
                "  /code run <コード>      — サンドボックス実行\n"
                "  /code test <コード>     — テストコード生成\n"
                "  /code explain <コード>  — コード解説\n"
                "  /review <コード>        — レビュー（省略形）\n"
                "  /fix <エラー>           — 修正提案（省略形）\n"
                "  /run <コード>           — 実行（省略形）\n"
                "  /explain <コード>       — 解説（省略形）\n"
                "  /test <コード>          — テスト生成（省略形）"
            )

        m = CMD_SLASH_CODE.match(user_input)
        if m:
            sub = (m.group(1) or "analyze").lower()
            body = m.group(2).strip()
            _slash_code_dispatch = {
                "analyze": ai._handle_code_analyze,
                "review":  ai._handle_code_review,
                "fix":     ai._handle_code_fix,
                "run":     ai._handle_code_run,
                "test":    ai._handle_code_test,
                "explain": ai._handle_code_explain,
            }
            handler = _slash_code_dispatch.get(sub, ai._handle_code_analyze)
            return handler(body)

        m = CMD_SLASH_REVIEW.match(user_input)
        if m:
            return ai._handle_code_review(m.group(1).strip())

        m = CMD_SLASH_FIX.match(user_input)
        if m:
            return ai._handle_code_fix(m.group(1).strip())

        m = CMD_SLASH_RUN.match(user_input)
        if m:
            return ai._handle_code_run(m.group(1).strip())

        m = CMD_SLASH_EXPLAIN.match(user_input)
        if m:
            return ai._handle_code_explain(m.group(1).strip())

        m = CMD_SLASH_TEST.match(user_input)
        if m:
            return ai._handle_code_test(m.group(1).strip())

        # ─── コードエンジン コマンド（自然言語） ──────────────────

        m = CMD_CODE_ANALYZE.match(user_input)
        if m:
            return ai._handle_code_analyze(m.group(4).strip())

        m = CMD_CODE_REVIEW.match(user_input)
        if m:
            return ai._handle_code_review(m.group(4).strip())

        m = CMD_CODE_FIX.match(user_input)
        if m:
            return ai._handle_code_fix(m.group(5).strip())

        m = CMD_CODE_TEST.match(user_input)
        if m:
            return ai._handle_code_test(m.group(4).strip())

        m = CMD_CODE_EXPLAIN.match(user_input)
        if m:
            return ai._handle_code_explain(m.group(4).strip())

        m = CMD_CODE_FILE.match(user_input)
        if m:
            return ai._handle_code_file(m.group(4).strip())

        m = CMD_CODE_RUN.match(user_input)
        if m:
            return ai._handle_code_run(m.group(4).strip())

        # ─── ドキュメント出力コマンド ──────────────────

        m = CMD_EXPORT_WORD.match(user_input)
        if m:
            return ai._handle_export("word", m.group(3).strip())

        m = CMD_EXPORT_PPTX.match(user_input)
        if m:
            return ai._handle_export("pptx", m.group(3).strip())

        m = CMD_EXPORT_EXCEL.match(user_input)
        if m:
            return ai._handle_export("excel", m.group(3).strip())

        m = CMD_EXPORT_AUTO.match(user_input)
        if m:
            return ai._handle_export("word", m.group(3).strip())

        # ─── Sprint 2.1: セキュリティコマンド ──────────────────

        if CMD_SECURITY.match(user_input):
            return ai._run_security_check()

        if CMD_BACKUP.match(user_input):
            if "一覧" in user_input or "リスト" in user_input:
                return ai._show_backup_list()
            return ai._run_backup()

        m = CMD_LOCKDOWN.match(user_input)
        if m:
            reason = m.group(2).strip() or "手動実行"
            return ai._run_lockdown(reason)

        if CMD_UNLOCK.match(user_input):
            return ai._run_unlock()

        # ─── Sprint J: サーバー・自律行動コマンド ──────────────

        if CMD_SERVER_STATUS.match(user_input):
            return ai._server_status()

        if CMD_SERVER_DOCKER.match(user_input):
            return ai._server_docker()

        if CMD_SERVER_SYNC.match(user_input):
            return ai._server_sync()

        if CMD_SERVER_SETUP.match(user_input):
            return ai._server_setup_guide()

        if CMD_PROACTIVE.match(user_input):
            return ai._proactive_talk()

        # ─── Sprint K: 国産AI進化コマンド ──────────────────────

        if CMD_KNOWLEDGE.match(user_input):
            kg = getattr(ai, "knowledge_graph", None)
            if kg:
                return kg.get_user_world_summary()
            return "知識グラフがまだ初期化されていないよ。"

        if CMD_RELATIONSHIP.match(user_input):
            evo = getattr(ai, "personality_evo", None)
            if evo:
                return evo.get_relationship_display()
            return "関係性トラッカーがまだ初期化されていないよ。"

        if CMD_GROWTH.match(user_input):
            evo = getattr(ai, "personality_evo", None)
            if evo:
                return evo.get_growth_summary()
            return "成長システムがまだ初期化されていないよ。"

        if CMD_QUALITY.match(user_input):
            ev = getattr(ai, "response_evaluator", None)
            if ev:
                return ev.get_quality_summary()
            return "品質評価システムがまだ初期化されていないよ。"

        # ─── ヤマト計画コマンド ───────────────────────────────

        if CMD_YAMATO_DASH.match(user_input):
            arch = getattr(ai, "yamato_arch", None)
            if arch:
                return arch.get_dashboard()
            return "ヤマトアーキテクチャがまだ初期化されていないよ。"

        if CMD_MOE_STATUS.match(user_input):
            moe = getattr(ai, "moe_router", None)
            if moe:
                return moe.get_status_text()
            return "MoEルーターがまだ初期化されていないよ。"

        if CMD_LEARNING_STATUS.match(user_input):
            cl = getattr(ai, "continuous_learner", None)
            if cl:
                return cl.get_status_text()
            return "継続学習エンジンがまだ初期化されていないよ。"

        if CMD_SYNTH_GEN.match(user_input):
            sg = getattr(ai, "synthetic_gen", None)
            if sg:
                if "生成" in user_input or "作成" in user_input:
                    results = sg.generate_batch(count=10)
                    return f"\U0001f9ec 合成データを{len(results)}件生成したよ！\n{sg.get_status_text()}"
                return sg.get_status_text()
            return "合成データ生成がまだ初期化されていないよ。"

        if CMD_VERIFY_STATUS.match(user_input):
            mv = getattr(ai, "multi_verifier", None)
            if mv:
                return mv.get_status_text()
            return "マルチエージェント検証がまだ初期化されていないよ。"

        # ─── データエクスポート ────────────────────────────────
        m = CMD_DATA_EXPORT.match(user_input)
        if m:
            return self._handle_data_export(m.group(1).strip())

        # ─── パーソナリティカード ──────────────────────────────
        if CMD_PERSONALITY_CARD.match(user_input):
            return self._handle_personality_card()

        # ─── ユーザープロファイル ──────────────────────────────
        m = CMD_USER_PROFILE.match(user_input)
        if m:
            return self._handle_user_register(m.group(1).strip())

        m = CMD_USER_SWITCH.match(user_input)
        if m:
            return self._handle_user_switch(m.group(1).strip())

        if CMD_USER_LIST.match(user_input):
            return self._handle_user_list()

        # ─── ヘルスチェック ───────────────────────────────────
        if CMD_HEALTH.match(user_input):
            return self._handle_health()

        return None

    # ─── 内部ヘルパ ───────────────────────────────────

    def _handle_diary(self, user_input: str) -> str:
        ai = self.ai
        if "書いて" in user_input:
            entry = ai.diary.write_today(
                emotion_snapshot=ai.emotion.state.to_dict()
            )
            if not entry:
                return "今日はまだあまり話してないから書けることが少ないかな。もう少し話そう！"
            return ai.diary.format_for_display(entry)
        entry = ai.diary.get_entry()
        if entry:
            return ai.diary.format_for_display(entry)
        entry = ai.diary.write_today(
            emotion_snapshot=ai.emotion.state.to_dict()
        )
        if entry:
            return ai.diary.format_for_display(entry)
        return "今日の日記はまだ書いてないよ。もう少し話してから見てね！"

    def _handle_data_export(self, arg: str) -> str:
        """データエクスポートコマンドの処理"""
        ai = self.ai
        exporter = getattr(ai, "data_exporter", None)
        if exporter is None:
            return "データエクスポーターがまだ初期化されていないよ。"

        from pathlib import Path

        export_dir = getattr(ai, "base_dir", Path(".")) / "data" / "exports"
        fmt = "json"
        target = "all"

        if arg:
            lower = arg.lower()
            if "csv" in lower:
                fmt = "csv"
            if "会話" in arg:
                target = "conversations"
            elif "記憶" in arg:
                target = "memories"
            elif "学習" in arg:
                target = "learning"

        try:
            results = []
            ext = fmt
            if target in ("all", "conversations"):
                out = export_dir / f"conversations.{ext}"
                count = exporter.export_conversations(out, fmt=fmt)
                results.append(f"会話: {count}件 → {out}")
            if target in ("all", "memories"):
                out = export_dir / f"memories.{ext}"
                count = exporter.export_memories(out, fmt=fmt)
                results.append(f"記憶: {count}件 → {out}")
            if target in ("all", "learning"):
                out = export_dir / "learning.json"
                count = exporter.export_learning(out)
                results.append(f"学習: {count}件 → {out}")

            if not results:
                return "エクスポート対象が見つからなかったよ。"
            header = f"データエクスポート完了（{fmt}）"
            return header + "\n" + "\n".join(f"  {r}" for r in results)
        except FileNotFoundError as e:
            return f"エクスポートに失敗したよ: {e}"
        except Exception as e:
            logger.error("データエクスポート失敗: %s", e)
            return f"エクスポート中にエラーが発生したよ: {e}"

    def _handle_personality_card(self) -> str:
        """パーソナリティカードコマンドの処理"""
        ai = self.ai
        card_mod = getattr(ai, "personality_card", None)
        if card_mod is None:
            return "パーソナリティカードがまだ初期化されていないよ。"

        stats = {}
        # 会話カウント
        if hasattr(ai, "memory") and ai.memory is not None:
            try:
                stats["memory_count"] = len(ai.memory.get_all())
            except Exception:
                pass
        # 感情パターン
        if hasattr(ai, "emotion_history") and ai.emotion_history is not None:
            try:
                stats["emotion_patterns"] = ai.emotion_history.get_pattern_summary()
            except Exception:
                pass
        # トピック
        if hasattr(ai, "topic_tracker") and ai.topic_tracker is not None:
            try:
                stats["top_topics"] = ai.topic_tracker.get_top_topics(5)
            except Exception:
                pass

        try:
            card = card_mod.generate(stats)
            return card_mod.summarize(card)
        except Exception as e:
            logger.error("パーソナリティカード生成失敗: %s", e)
            return f"パーソナリティカードの生成中にエラーが発生したよ: {e}"

    def _handle_user_register(self, name: str) -> str:
        """ユーザープロファイル登録コマンドの処理"""
        ai = self.ai
        mgr = getattr(ai, "user_profile_mgr", None)
        if mgr is None:
            return "ユーザープロファイル管理がまだ初期化されていないよ。"

        try:
            profile_dir = mgr.create(name)
            return f"ユーザー「{name}」を登録したよ！（{profile_dir}）"
        except FileExistsError:
            return f"「{name}」はもう登録済みだよ。"
        except ValueError as e:
            return f"登録できなかったよ: {e}"
        except Exception as e:
            logger.error("ユーザー登録失敗: %s", e)
            return f"登録中にエラーが発生したよ: {e}"

    def _handle_user_switch(self, name: str) -> str:
        """ユーザープロファイル切替コマンドの処理"""
        ai = self.ai
        mgr = getattr(ai, "user_profile_mgr", None)
        if mgr is None:
            return "ユーザープロファイル管理がまだ初期化されていないよ。"

        try:
            mgr.switch(name)
            return f"ユーザーを「{name}」に切り替えたよ！"
        except FileNotFoundError:
            return f"「{name}」というユーザーが見つからないよ。先に登録してね。"
        except Exception as e:
            logger.error("ユーザー切替失敗: %s", e)
            return f"切り替え中にエラーが発生したよ: {e}"

    def _handle_user_list(self) -> str:
        """ユーザープロファイル一覧コマンドの処理"""
        ai = self.ai
        mgr = getattr(ai, "user_profile_mgr", None)
        if mgr is None:
            return "ユーザープロファイル管理がまだ初期化されていないよ。"

        profiles = mgr.list_profiles()
        if not profiles:
            return "まだユーザーが登録されていないよ。「ユーザー登録 名前」で登録してね。"

        current = mgr.current()
        lines = ["── ユーザー一覧 ──"]
        for name in profiles:
            marker = " ← 現在" if name == current else ""
            lines.append(f"  {name}{marker}")
        return "\n".join(lines)

    def _handle_health(self) -> str:
        """システムヘルスチェックを実行して結果を整形して返す"""
        ai = self.ai
        hc = getattr(ai, "health_check", None)
        if hc is None:
            return "ヘルスチェックモジュールが初期化されていないよ。"

        try:
            results = hc.run()
        except Exception as e:
            logger.exception("ヘルスチェック実行エラー")
            return f"ヘルスチェック中にエラーが起きたよ: {e}"

        status_icons = {
            hc.STATUS_OK: "\u2705",
            hc.STATUS_WARN: "\u26a0\ufe0f",
            hc.STATUS_FAIL: "\u274c",
        }

        lines = ["\U0001f3e5 システムヘルスチェック結果"]
        for name, health in results.items():
            icon = status_icons.get(health.status, "\u2753")
            lines.append(f"  {icon} {name}: {health.message}")

        ok_count = sum(1 for r in results.values() if r.status == hc.STATUS_OK)
        warn_count = sum(1 for r in results.values() if r.status == hc.STATUS_WARN)
        fail_count = sum(1 for r in results.values() if r.status == hc.STATUS_FAIL)
        total = len(results)

        lines.append("")
        if fail_count > 0:
            lines.append(f"\U0001f534 {fail_count}件の問題が見つかったよ。確認してね！")
        elif warn_count > 0:
            lines.append(f"\U0001f7e1 {warn_count}件の注意項目があるよ。（{ok_count}/{total} OK）")
        else:
            lines.append(f"\U0001f7e2 全項目正常だよ！（{ok_count}/{total} OK）")

        return "\n".join(lines)

    def _handle_mode(self, user_input: str) -> str | None:
        """モード切替コマンドの処理"""
        ai = self.ai
        mode_mgr = getattr(ai, "mode_manager", None)
        if mode_mgr is None:
            return None

        from core.mode_manager import FAMILY_MODE, AGENT_MODE, LEARNING_MODE, CREATIVE_MODE

        # モード状態確認
        if CMD_MODE_STATUS.match(user_input):
            status = mode_mgr.get_status()
            mode_names = {
                FAMILY_MODE: "家族モード 💗",
                AGENT_MODE: "お仕事モード 💼",
                LEARNING_MODE: "学習モード 📚",
                CREATIVE_MODE: "創作モード 🎨",
            }
            current = mode_names.get(status["current_mode"], status["current_mode"])
            usage = status["session_usage"]
            lines = [
                f"現在のモード: {current}",
                f"セッション合計: {status['total_turns']}ターン",
                "── モード別使用回数 ──",
            ]
            for mode, count in usage.items():
                name = mode_names.get(mode, mode)
                lines.append(f"  {name}: {count}回")
            return "\n".join(lines)

        # 直接モード指定
        target = None
        if CMD_MODE_FAMILY.match(user_input):
            target = FAMILY_MODE
        elif CMD_MODE_AGENT.match(user_input):
            target = AGENT_MODE
        elif CMD_MODE_LEARN.match(user_input):
            target = LEARNING_MODE
        elif CMD_MODE_CREATIVE.match(user_input):
            target = CREATIVE_MODE
        elif CMD_MODE_SWITCH.match(user_input):
            m = CMD_MODE_SWITCH.match(user_input)
            mode_text = m.group(1).strip() if m else ""
            mode_map = {
                "家族": FAMILY_MODE, "ファミリー": FAMILY_MODE,
                "仕事": AGENT_MODE, "エージェント": AGENT_MODE, "作業": AGENT_MODE,
                "学習": LEARNING_MODE, "勉強": LEARNING_MODE,
                "創作": CREATIVE_MODE, "クリエイティブ": CREATIVE_MODE,
            }
            target = mode_map.get(mode_text)
            if target is None:
                return f"「{mode_text}」というモードは知らないよ。家族・仕事・学習・創作 から選んでね。"

        if target is not None:
            msg = mode_mgr.switch_mode(target)
            if msg:
                return msg
            else:
                mode_names_simple = {
                    FAMILY_MODE: "家族モード",
                    AGENT_MODE: "お仕事モード",
                    LEARNING_MODE: "学習モード",
                    CREATIVE_MODE: "創作モード",
                }
                return f"今はもう{mode_names_simple.get(target, target)}だよ♪"

        return None

    def _handle_voice_id(self, user_input: str) -> str | None:
        """声紋認証コマンドの処理"""
        ai = self.ai
        voice_id = getattr(ai, "voice_id", None)
        if voice_id is None:
            return None

        # 声紋状態確認
        if CMD_VOICE_STATUS.match(user_input):
            current_user = voice_id.get_current_user()
            trust = voice_id.get_trust_level()
            profiles = getattr(voice_id, "_profiles", {})
            lines = ["🎤 声紋認証ステータス"]
            if current_user:
                lines.append(f"  現在のユーザー: {current_user.name}")
                lines.append(f"  信頼レベル: {trust}")
                has_voice = bool(getattr(current_user, "voice_features", None))
                lines.append(f"  声紋データ: {'✅ 登録済み' if has_voice else '❌ 未登録'}")
            else:
                lines.append("  ユーザー: 未識別")
            lines.append(f"  登録ユーザー数: {len(profiles)}")
            if profiles:
                for uid, prof in profiles.items():
                    v = "🎤" if getattr(prof, "voice_features", None) else "📝"
                    lines.append(f"    {v} {prof.name} (trust={prof.trust_level})")
            return "\n".join(lines)

        # 声紋登録
        m = CMD_VOICE_REGISTER.match(user_input)
        if m:
            name = m.group(1).strip() if m.group(1) else ""
            try:
                if hasattr(voice_id, "register_voice") and name:
                    result = voice_id.register_voice(name)
                    if result.get("success"):
                        return f"🎤 {name}さんの声紋を登録したよ！これからは声で誰だかわかるね♪"
                    else:
                        return f"🎤 声紋登録に失敗しちゃった…: {result.get('error', '不明なエラー')}"
                elif name:
                    voice_id.register_user(name)
                    return f"🎤 {name}さんを登録したよ！（名前ベース識別）"
                else:
                    return "🎤 名前を教えてね。例: 声紋登録 しょうた"
            except Exception as e:
                logger.warning("声紋登録失敗: %s", e)
                return f"🎤 声紋登録でエラーが起きちゃった…: {e}"

        # 声紋認証
        if CMD_VOICE_IDENTIFY.match(user_input):
            try:
                if hasattr(voice_id, "identify_by_voice"):
                    result = voice_id.identify_by_voice()
                    if result and result.get("matched"):
                        name = result["name"]
                        score = result.get("score", 0)
                        return f"🎤 声紋照合完了！ {name}さんだね（類似度: {score:.1%}）"
                    else:
                        return "🎤 声紋が一致するユーザーが見つからなかったよ。「声紋登録 名前」で登録してね。"
                else:
                    return "🎤 声紋認証はまだマイク録音に対応していないよ。「声紋登録 名前」で名前ベースの登録ができるよ。"
            except ImportError:
                return "🎤 声紋認証に必要なライブラリ（librosa, sounddevice）がインストールされていないよ。"
            except Exception as e:
                logger.warning("声紋認証失敗: %s", e)
                return f"🎤 声紋認証でエラーが起きちゃった…: {e}"

        return None

    # ─── 音声管理コマンド ──────────────────────────────

    def _handle_voice_management(self, user_input: str) -> str | None:
        """音声エンジン確認・切替・テストの処理"""
        ai = self.ai
        tts = getattr(ai, "tts", None)

        # /voice または 音声確認 — 現在の音声エンジン情報を表示
        if CMD_VOICE_INFO.match(user_input):
            return self._voice_info(tts)

        # 音声一覧 — 使える音声のリスト
        if CMD_VOICE_LIST.match(user_input):
            return self._voice_list(tts)

        # 音声テスト — 指定モードで短いフレーズを読み上げ
        m = CMD_VOICE_TEST.match(user_input)
        if m:
            mode = m.group(1).strip() if m.group(1) else ""
            return self._voice_test(tts, mode)

        # 音声切替 — neural / say / off
        m = CMD_VOICE_SWITCH.match(user_input)
        if m:
            target = m.group(1).strip().lower() if m.group(1) else ""
            return self._voice_switch(tts, target, ai)

        return None

    def _voice_info(self, tts) -> str:
        """現在の音声エンジン情報を返す"""
        lines = ["🔊 音声エンジン情報\n"]

        if tts is None:
            lines.append("  音声エンジン: 無効")
            lines.append("\n💡 settings.json の tts.enabled を true にしてね")
            return "\n".join(lines)

        engine_name = type(tts).__name__
        enabled = getattr(tts, "enabled", False)
        lines.append(f"  エンジン: {engine_name}")
        lines.append(f"  有効: {'✅ ON' if enabled else '❌ OFF'}")

        # NeuralTTSEngine 固有情報
        audio_mode = getattr(tts, "audio_mode", None)
        if audio_mode:
            mode_label = "🧠 ニューラル (edge-tts)" if audio_mode == "neural" else "🍎 macOS say"
            lines.append(f"  現在のモード: {mode_label}")

        voice = getattr(tts, "voice", None)
        if voice:
            lines.append(f"  ニューラル音声: {voice}")

        say_voice = getattr(tts, "_say_voice", None)
        if say_voice:
            lines.append(f"  フォールバック音声: {say_voice}")

        emotion = getattr(tts, "_emotion", None)
        if emotion:
            lines.append(f"  現在の感情: {emotion}")

        fail_count = getattr(tts, "_neural_failed_count", None)
        if fail_count is not None:
            max_fail = getattr(tts, "_max_neural_failures", 3)
            lines.append(f"  連続失敗: {fail_count}/{max_fail}")

        lines.append("\n💡 コマンド:")
        lines.append("  音声テスト       テストフレーズを読み上げ")
        lines.append("  音声一覧         利用可能な音声の一覧")
        lines.append("  音声切替 neural   ニューラル音声に切替")
        lines.append("  音声切替 say      macOS say に切替")
        lines.append("  音声切替 off      音声をオフ")
        return "\n".join(lines)

    def _voice_list(self, tts) -> str:
        """利用可能なニューラル音声のリストを返す"""
        lines = ["🔊 利用可能な日本語音声\n"]

        # ニューラル音声
        from core.neural_tts import EDGE_TTS_AVAILABLE, NeuralTTSEngine, NEURAL_VOICES
        lines.append("【ニューラル音声 (edge-tts)】")
        if EDGE_TTS_AVAILABLE:
            for key, voice_name in NEURAL_VOICES.items():
                current = ""
                if tts and getattr(tts, "voice", None) == voice_name:
                    current = " ← 現在"
                lines.append(f"  🎙️ {key}: {voice_name}{current}")

            # リモートの全音声リストを取得（ネットワーク必要）
            try:
                all_voices = NeuralTTSEngine.available_voices()
                if all_voices:
                    lines.append(f"\n  全 {len(all_voices)} 個の日本語音声が利用可能:")
                    for v in all_voices:
                        gender_icon = "👩" if v["gender"] == "Female" else "👨"
                        lines.append(f"    {gender_icon} {v['name']}")
            except Exception:
                lines.append("  (オンラインリストの取得に失敗)")
        else:
            lines.append("  ❌ edge-tts 未インストール")
            lines.append("  pip install edge-tts でインストールしてね")

        # macOS say
        lines.append("\n【macOS say 音声】")
        lines.append("  🍎 Kyoko (日本語コンパクト)")
        lines.append("  🍎 O-Ren (日本語拡張)")

        lines.append(
            "\n💡 切替例: 音声切替 neural"
        )
        return "\n".join(lines)

    def _voice_test(self, tts, mode: str) -> str:
        """テストフレーズを指定モードで読み上げる"""
        if tts is None or not getattr(tts, "enabled", False):
            return "🔊 音声が無効です。settings.json の tts.enabled を true にしてね"

        test_phrase = "こんにちは！アイだよ。今日も一緒に頑張ろうね！"

        if mode in ("neural", "ニューラル"):
            # ニューラル音声で強制テスト
            from core.neural_tts import EDGE_TTS_AVAILABLE
            if not EDGE_TTS_AVAILABLE:
                return "🔊 edge-tts がインストールされていません。pip install edge-tts"
            if hasattr(tts, "_speak_neural"):
                tts._neural_failed_count = 0
                tts._speak_neural(test_phrase, "happy")
                return "🔊 ニューラル音声のテスト完了！"
            return "🔊 現在のエンジンはニューラル音声に対応していません"

        elif mode in ("say", "マック"):
            if hasattr(tts, "_speak_say_fallback"):
                tts._speak_say_fallback(test_phrase)
                return "🔊 macOS say 音声のテスト完了！"
            return "🔊 macOS say フォールバックは利用できません"

        else:
            # 通常モードでテスト
            tts.speak(test_phrase, blocking=True)
            engine_name = type(tts).__name__
            audio_mode = getattr(tts, "audio_mode", "unknown")
            return f"🔊 音声テスト完了！（エンジン: {engine_name}, モード: {audio_mode}）"

    def _voice_switch(self, tts, target: str, ai) -> str:
        """音声モードを切り替える"""
        if not target:
            return (
                "🔊 切替先を指定してね:\n"
                "  音声切替 neural  → ニューラル音声 (edge-tts)\n"
                "  音声切替 say     → macOS say 音声\n"
                "  音声切替 off     → 音声オフ"
            )

        if target in ("neural", "ニューラル"):
            from core.neural_tts import EDGE_TTS_AVAILABLE, create_neural_tts
            if not EDGE_TTS_AVAILABLE:
                return "🔊 edge-tts がインストールされていません。\npip install edge-tts"
            cfg = ai.settings.get("tts", {})
            ai.tts = create_neural_tts(cfg)
            return "🔊 ニューラル音声 (edge-tts) に切り替えたよ！🧠\nMicrosoft Neural TTS で自然な音声をお届けするね♪"

        elif target in ("say", "マック", "macos"):
            from core.tts import TTSEngine
            cfg = ai.settings.get("tts", {})
            ai.tts = TTSEngine(
                enabled=cfg.get("enabled", True),
                voice=cfg.get("voice", "Kyoko"),
                rate=cfg.get("rate", 175),
            )
            return "🔊 macOS say 音声に切り替えたよ！🍎"

        elif target in ("off", "オフ", "無効"):
            if tts:
                tts.enabled = False
            return "🔊 音声をオフにしたよ。「音声切替 neural」でいつでも戻せるよ♪"

        elif target in ("on", "オン", "有効"):
            if tts:
                tts.enabled = True
            return "🔊 音声をオンにしたよ♪"

        else:
            return (
                f"🔊 「{target}」は不明な切替先だよ。\n"
                "  neural / say / off / on から選んでね"
            )

    # ─── イントネーション学習コマンド ──────────────────

    def _handle_prosody_learning(self, user_input: str) -> str | None:
        """人間の声からイントネーションを学習するコマンド処理。"""
        ai = self.ai
        learner = getattr(ai, "prosody_learner", None)
        if learner is None:
            return None

        # 状態確認
        if CMD_PROSODY_STATUS.match(user_input):
            return learner.get_status_text()

        # ファイルから学習
        m = CMD_PROSODY_FILE.match(user_input)
        if m:
            file_path = m.group(1).strip()
            result = learner.learn_from_file(file_path)
            if result.get("success"):
                self._apply_learned_prosody(ai, learner)
                return f"🎓 {result['message']}"
            return f"❌ {result['message']}"

        # マイクから録音学習
        if CMD_PROSODY_LEARN.match(user_input):
            return self._prosody_record_and_learn(ai, learner)

        # 学習結果を適用
        if CMD_PROSODY_APPLY.match(user_input):
            if not learner.has_learned():
                return "🎓 まだ学習データがないよ。「イントネーション学習」で声を聞かせてね！"
            self._apply_learned_prosody(ai, learner)
            return "🎓 学習したイントネーションを適用したよ！次の発話から反映されるね♪"

        # リセット
        if CMD_PROSODY_RESET.match(user_input):
            learner.reset()
            tts = getattr(ai, "tts", None)
            if hasattr(tts, "apply_learned_prosody"):
                tts.apply_learned_prosody({})
            return "🎓 イントネーション学習をリセットしたよ。デフォルトの話し方に戻るね。"

        return None

    def _prosody_record_and_learn(self, ai, learner) -> str:
        """マイクから録音してプロソディを学習する。"""
        try:
            import sounddevice  # noqa: F401
        except ImportError:
            return "🎓 マイク録音に必要な sounddevice がインストールされていません"

        lines = [
            "🎓 イントネーション学習を始めるよ！",
            "",
            "自然な声で以下のフレーズを読んでね:",
            "「こんにちは、今日はいい天気ですね。一緒に散歩に行きませんか？」",
            "",
            "5秒間の録音を開始します...",
        ]
        print("\n".join(lines), flush=True)

        result = learner.record_and_learn(duration_sec=5.0)
        if result.get("success"):
            self._apply_learned_prosody(ai, learner)
            return f"🎓 {result['message']}\n\n💡 学習を重ねるほど精度が上がるよ！もう一度「イントネーション学習」で追加学習できるよ。"
        return f"❌ {result['message']}"

    @staticmethod
    def _apply_learned_prosody(ai, learner) -> None:
        """学習結果を TTS エンジンに適用する。"""
        from core.neural_tts import NeuralTTSEngine
        tts = getattr(ai, "tts", None)
        if isinstance(tts, NeuralTTSEngine):
            overrides = learner.get_tts_overrides()
            tts.apply_learned_prosody(overrides)
