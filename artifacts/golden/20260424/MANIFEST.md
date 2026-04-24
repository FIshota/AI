# Golden Output Manifest — 20260424
Collected: 2026-04-24 06:53:51 JST
Host: current PC (pre-migration baseline)

## ai-chan
Base: `ai-chan/artifacts/golden/20260424`

| file | sha256 | lines | size |
|---|---|---|---|
| `_synthetic_anniv_data/tenants/self/anniversaries.json` | `d8e962532287451fc6f1a10531231314afcd418f99f20554d4a8e469a50945f5` | 15 | 285 |
| `_synthetic_emotion_history.json` | `7f6195f499eca1862082dbb368d2665e759259bc5a22777e16d1cc1c207f9d09` | 9 | 447 |
| `_synthetic_search.db` | `d554aa30e6d1ce53aa3a0cd9517b315720469e9492b5899cf4a4c082bd00b0f0` | - | 40960 |
| `anniversaries.ics` | `1fff6e2437bd0dab5d672c398a6190c352c38d1c7ef0ce086721b64da9df3f74` | 29 | 596 |
| `config_hashes.txt` | `306d170b5b994e3fbb20c036ddd506af4b6f3b68a0cea73ceb212e8b0d1861c7` | 5 | 472 |
| `emotion_report_week.txt` | `da0a05efa55c1e44d60873ece05e286e1f295ba94446437f2d073db5bb4622b6` | 3 | 124 |
| `export_anniv.err.log` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0 | 0 |
| `import_smoke.txt` | `9306260000a3fbecb2800820b9e0da6794f44b795e6f7afab0baec4586c812dc` | 6 | 119 |
| `pytest_full.txt` | `34839423225a9805a170f62d8813c652057deea8fa0084278c533aafae9f6ae3` | 37 | 2796 |
| `search_conversations.err.log` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0 | 0 |
| `search_conversations.json` | `b3442a8a4b3b44d3374be9bebc43a1cfc277919e337f7dd38ed6a49a9632cc93` | 17 | 288 |

## hinomoto-model
Base: `hinomoto-model/artifacts/golden/20260424`

| file | sha256 | lines | size |
|---|---|---|---|
| `hinomoto_checkpoints.txt` | `176ea7ce9cfff8766b06d0913eb80b879c56e895f001f984cfcf4f20f9739aae` | 84 | 15691 |
| `hinomoto_pytest.txt` | `96d922bc603d2fb66c88e0b784d04b7fe1c9ccd1b43f99ce88accbe3b3655686` | 202 | 16677 |
| `validate_recipes.txt` | `b5a6f0dd712810940801d2ead9056c08da83475483076c720bf5d2036cc6c249` | 5 | 111 |

## 新 PC での照合方法

```bash
# ai-chan
cd new-pc-repo/ai-chan
mkdir -p artifacts/golden_new/20260424
python3 -m pytest -q --tb=no > artifacts/golden_new/20260424/pytest_full.txt
python3 scripts/generate_emotion_report.py --window week --no-plot \
    --input artifacts/golden/20260424/_synthetic_emotion_history.json \
    > artifacts/golden_new/20260424/emotion_report_week.txt
shasum -a 256 config/access_control.json config/persona.json \
    config/screenshot_sensitive_patterns.yaml.example \
    config/settings_schema.json requirements.txt \
    > artifacts/golden_new/20260424/config_hashes.txt
# diff 対象
diff artifacts/golden/20260424/config_hashes.txt \
     artifacts/golden_new/20260424/config_hashes.txt
diff artifacts/golden/20260424/emotion_report_week.txt \
     artifacts/golden_new/20260424/emotion_report_week.txt

# hinomoto-model
cd ../hinomoto-model
mkdir -p artifacts/golden_new/20260424
python3 -m pytest -q --tb=no > artifacts/golden_new/20260424/hinomoto_pytest.txt
python3 scripts/validate_recipes.py > artifacts/golden_new/20260424/validate_recipes.txt
diff artifacts/golden/20260424/validate_recipes.txt \
     artifacts/golden_new/20260424/validate_recipes.txt
```

## Notes
- pytest 合格数は環境依存のため、passed/failed 数の一致を優先確認
- `_synthetic_*` prefix の合成データは golden の再現性を確保するため付属
- checkpoints は head/tail 1KB sha256 のみ記録 (全体ハッシュではない)
