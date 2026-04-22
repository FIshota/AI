"""Entry point: inject fake core.llm, then run the real worker."""
import sys, importlib, types
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tests" / "support"))

# Inject fake before worker imports real core.llm
import fake_core_llm  # noqa
sys.modules["core.llm"] = fake_core_llm

from scripts.ai_chan_llm_worker import main  # noqa
raise SystemExit(main())
