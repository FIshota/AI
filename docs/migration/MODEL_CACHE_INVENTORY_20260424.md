# §10 Model / Cache Inventory — 2026-04-24

## HuggingFace cache: **10 GB** at `~/.cache/huggingface/`

### Models
| Model | Purpose |
|---|---|
| `Qwen/Qwen2.5-3B-Instruct` | Fallback LM |
| `Systran/faster-whisper-large-v3` | High-accuracy ASR |
| `Systran/faster-whisper-medium` | Balanced ASR |
| `Systran/faster-whisper-small` | Fast ASR |
| `Systran/faster-whisper-tiny` | Ultra-fast ASR |
| `mlx-community/whisper-small-mlx` | MLX ASR |
| `mlx-community/whisper-tiny-mlx` | MLX ASR |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | Embeddings |
| `vikhyatk/moondream2` | Vision |

### Datasets
- `elyza/ELYZA-tasks-100` — Japanese eval
- `kunishou/databricks-dolly-15k-ja` — SFT
- `shunk031/JGLUE` — JP GLUE eval
- `wikimedia/wikipedia` — pretraining corpus

## GGUF files
- `ai-chan/models/sarashina2-7b.Q4_K_M.gguf` — primary llama.cpp model

## Not installed
- ollama (not present on this machine)
- pip mirror (default PyPI)

## Migration strategy

### Option A — re-download on new Mac (recommended, cleanest)
Pros: guaranteed integrity, automatic latest revisions
Cons: ~10 GB of bandwidth + time
```bash
# Models auto-download on first use via transformers/huggingface_hub
# Or pre-warm:
python3 -c "from transformers import AutoTokenizer; AutoTokenizer.from_pretrained('Qwen/Qwen2.5-3B-Instruct')"
```

### Option B — rsync cache (fast but big)
```bash
# Old Mac
rsync -av ~/.cache/huggingface/ /Volumes/MigrationDisk/hf_cache/
# New Mac
rsync -av /Volumes/MigrationDisk/hf_cache/ ~/.cache/huggingface/
```
Save ~10 GB bandwidth, but verify fetch works post-copy (locks may need reset):
```bash
rm -rf ~/.cache/huggingface/hub/.locks
```

### Option C — selective migration
Only copy models you actively use; let unused ones re-download lazily. Saves 5-7 GB.

## GGUF migration
`sarashina2-7b.Q4_K_M.gguf` is large (likely ~4 GB). Path: `ai-chan/models/`
- Already inside repo but `.gitignore` likely excludes it (check)
- Must be copied via external disk, not git

## Action checklist

- [ ] Decide Option A/B/C for HF cache (suggest **B** for offline-capable new-Mac setup)
- [ ] Copy `sarashina2-7b.Q4_K_M.gguf` to external disk
- [ ] Note HuggingFace token if used: `cat ~/.cache/huggingface/token` (migrate via 1Password)
