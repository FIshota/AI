# ~/.zshrc 旧 anaconda3 init 整理 提案

**ステータス**: 要ユーザー承認（自動実行していません）
**作成日**: 2026-04-24
**対象**: `~/.zshrc` 冒頭の conda initialize ブロック

## 該当ブロック（匿名化引用）

```zsh
# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
__conda_setup="$('~/opt/anaconda3/bin/conda' 'shell.zsh' 'hook' 2> /dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "~/opt/anaconda3/etc/profile.d/conda.sh" ]; then
        . "~/opt/anaconda3/etc/profile.d/conda.sh"
    else
        export PATH="~/opt/anaconda3/bin:$PATH"
    fi
fi
unset __conda_setup
# <<< conda initialize <<<
```

（実際のパスはホームディレクトリ絶対パス。L2〜L15）

## 移管先で不要な理由

1. **anaconda3 はもう使っていない**
   - 現在は システム Python 3.13 + venv 運用方針に統一予定（`docs/SETUP_VENV.md` 参照）
   - `~/opt/anaconda3/` は移管先マシンには存在しない → エラー出力が毎シェル起動時に発生する

2. **MLX / Apple Silicon 移行と衝突**
   - anaconda 配下の Python は x86_64 インタプリタで、Apple Silicon の MLX と互換しない
   - conda を残すと誤って x86_64 環境を activate してしまう事故が起きる

3. **起動コスト**
   - conda init は shell 起動を 100〜300ms 遅延させる。不要なら削る

## 削除手順

```bash
# バックアップ
cp ~/.zshrc ~/.zshrc.bak.$(date +%Y%m%d_%H%M%S)

# 手動削除（推奨）
# エディタで ~/.zshrc を開き、
#   # >>> conda initialize >>>
#   …
#   # <<< conda initialize <<<
# の 14 行（前後空行含め 15 行）を削除

# または sed 自動削除
sed -i.bak '/# >>> conda initialize >>>/,/# <<< conda initialize <<</d' ~/.zshrc

# 反映
exec zsh
# または
source ~/.zshrc
```

## 検証

```bash
# conda コマンドが not found になることを確認
which conda || echo "OK: conda is gone"

# シェル起動にエラーが出ないことを確認
zsh -i -c 'exit' 2>&1 | grep -i error || echo "OK: no startup error"
```

## 移管先での扱い

移管先マシンでは **このブロックは再作成しない**。Python は以下のいずれかで管理:

- `pyenv install 3.13.x`
- `brew install python@3.13`
- python.org 公式インストーラ

プロジェクトごとに `python3 -m venv .venv` で venv を切る（`docs/SETUP_VENV.md`）。

## 要確認

- [ ] anaconda3 配下に保存した独自環境が存在しないか事前確認
  ```bash
  ls ~/opt/anaconda3/envs/ 2>/dev/null
  ```
  もし重要な環境が残っていれば `conda env export` で YAML 化してから削除
- [ ] anaconda3 ディレクトリ自体の削除（`rm -rf ~/opt/anaconda3`）は別タスク
- [ ] 削除後、ログインシェルで他のスクリプトが `conda` を参照していないか grep
