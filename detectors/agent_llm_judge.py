"""`agent-llm-judge` is not a judge, and now it does not pretend to be one.

It was registered as a detector named "Agent — LLM-as-judge (the agent
itself)", it appeared in the detector dropdown beside the real judges, and
its own docstring said it "does NOT call any LLM": it built an
`OfflineDetector` and returned its spans. Someone choosing it from the
window believed a model had read their text. That is the defect this project
keeps finding - a control that looks like it works because nothing raises.

Two more things it did, both invisible:

* it dropped every character finding under 0.33, contradicting the rule the
  offline detector states for itself - a wrong dash is a fact about the
  text, so a low score there means "a small defect", not "probably nothing";
* it declared `includes_character_pass = False` while wrapping a detector
  that declares `True`, so `ui/worker.py` ran the character pass a **second**
  time over it and the window double-reported every non-keyboard character.

So the class is gone and the name is an alias. `--detector agent-llm-judge`
and an older `settings.json` keep working and now do, under the right label,
exactly what they were already doing.

**The real agent-as-judge workflow is unaffected and is the two CLI steps:**

    xaudit agent-scan ./src --json > candidates.json
    # the agent reads the candidates and writes judgments
    xaudit agent-judge ./src --judgments verdicts.json

Its findings are still stamped `agent-llm-judge` in `cli_impl/agentcmds.py`,
which is accurate there: an agent did the judging.
"""
from __future__ import annotations

from .factory import DetectorFactory

DetectorFactory.register_alias("agent-llm-judge", "offline")
