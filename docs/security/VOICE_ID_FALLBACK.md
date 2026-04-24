# Voice ID Fallback

Module: `core/voice_id_fallback.py`
Config: `config/voice_auth_challenges.yaml`
Tests: `tests/test_voice_id_fallback.py`

## Purpose

The voice ID pipeline occasionally returns a false-positive match against a
registered family member (papa / mama / etc.). This module adds a defense
layer that:

1. Detects linguistic **drift** between the current utterance and the
   subject's recent speech profile.
2. Applies a **challenge policy** (pre-registered passphrase or
   confirmation question) whenever drift or confidence suggests the
   match is unsafe.
3. **Demotes** the claimed subject to `guest` after repeated challenge
   failures.

It is intentionally loosely coupled: it consumes a `VoiceMatch` value
object produced upstream and never handles raw audio features.

## Threat Model

| Actor | Capability | Mitigation |
|-------|-----------|------------|
| Stranger physically present | Speaks in place of family; voice-ID engine returns false match | Drift detector flags unfamiliar lexical/topic profile; challenge prompt blocks escalation |
| Recording replay of family voice | Plays back short clip to impersonate | Confidence may be high but topic drift relative to conversation history is high; challenge required |
| Adversarial TTS clone | Generates plausible utterance | Unknown passphrase / pre-registered question prevents authorization |
| Curious family member | Tries to act as another member | Passphrase is per-subject and not shared |

Out of scope: root-level OS compromise, microphone tampering, social
engineering the user into revealing their passphrase.

## Decision Flow

```
+--------------+       +-----------------+      +-----------------+
| VoiceMatch   | --->  | DriftDetector   | ---> | FallbackPolicy  |
| (upstream)   |       | .score(...)     |      | .should_challenge|
+--------------+       +-----------------+      +-----------------+
                                                        |
                                                 challenge? yes
                                                        v
                                          +--------------------------+
                                          | challenge_prompt()       |
                                          | verify_response()        |
                                          +--------------------------+
                                                        |
                                 success                |         failure (3x)
                                        +---------------+---------------+
                                        v                               v
                              accept as claimed              demote to `guest`
```

Thresholds (from `FallbackPolicy`):

- `confidence < 0.7` → challenge
- `drift > 0.5` → challenge
- `failures >= 3` → demote to `guest` until a correct response arrives

## FAR / FRR Tradeoff

| Knob | Effect on FAR (false accept) | Effect on FRR (false reject) |
|------|------------------------------|-------------------------------|
| Raise `CONFIDENCE_THRESHOLD` (e.g. 0.8) | Lower FAR | Higher FRR, more friction |
| Raise `DRIFT_THRESHOLD` (e.g. 0.7) | Higher FAR | Lower FRR |
| Shorter `history_size` | Detector reacts faster to topic shifts → mixed | Unstable scoring for chatty users |
| More registered passphrases / questions | Lowers FRR (more valid answers) | Slightly raises FAR if questions are guessable |

Current defaults (`0.7` / `0.5` / `history_size=8`) bias toward low FAR.
Re-tuning should follow a real eval harness against recorded family
sessions; see `skills/eval-harness`.

## Privacy

- **Utterance text is never persisted.** `DriftDetector.observe` stores
  only: character length, token diversity ratio, keigo frequency, and a
  set of character bigrams. The original string is discarded.
- Profiles live in a per-process bounded `deque` (default 8 entries per
  subject). No disk writes. Restarting ai-chan clears all profiles.
- Passphrases and questions live in `config/voice_auth_challenges.yaml`.
  Operators are expected to treat this file as sensitive (do not commit
  real family secrets to any shared repository). The shipped sample
  values are placeholders.
- Failure counts and demotion state are also in-memory only.

## Usage Sketch

```python
from core.voice_id_fallback import (
    DriftDetector, FallbackPolicy, VoiceMatch, load_challenges_from_yaml
)

challenges = load_challenges_from_yaml("config/voice_auth_challenges.yaml")
policy = FallbackPolicy(challenges)
detector = DriftDetector()

def handle(match: VoiceMatch):
    drift = detector.score(match.utterance, match.claimed_subject_id)
    if policy.should_challenge(match, drift):
        prompt = policy.challenge_prompt(match.claimed_subject_id)
        response = ask_user(prompt)          # out of scope
        if not policy.verify_response(match.claimed_subject_id, response):
            return policy.effective_subject(match.claimed_subject_id)
    detector.observe(match.claimed_subject_id, match.utterance)
    return match.claimed_subject_id
```

## Related

- `core/voice_id.py` — upstream identification engine (untouched by this module).
- `docs/THREAT_MODEL.md` — broader household threat model.
- `docs/PRIVACY.md` — overall data handling commitments.
