"""Study cortex — learn critical theory, then reuse it in AOA.

Architecture (sLM-style, two phases):

1. **Learn** — curated theorem cards + spaced mastery (deterministic student model).
2. **Use** — mastered bridges inject into swarm prompts; export JSONL for a future
   LoRA/sLM adapter via :mod:`aoa.adapt.torch_lora`.

This is *not* training a neural LM in-process. It builds the corpus and mastery
loop first; fine-tuning is optional and offline.
"""

from aoa.study.cortex import StudyCortex
from aoa.study.curriculum import KnowledgeCard, all_cards, get_card
from aoa.study.mastery import StudyMastery, load_mastery, save_mastery

__all__ = [
    "StudyCortex",
    "KnowledgeCard",
    "StudyMastery",
    "all_cards",
    "get_card",
    "load_mastery",
    "save_mastery",
]
