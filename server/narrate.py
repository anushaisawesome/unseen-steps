"""Draft a line, check it, and rewrite it once if the checker rejects it.

Usage (try it on sample features):
    python server/narrate.py data/samples/features.json
"""

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from checker import check
from writer import write_line


@dataclass
class Result:
    line: str | None                                  # what gets spoken, or None for silence
    attempts: list[dict] = field(default_factory=list)  # every draft and its verdict, for the demo


def describe(features: dict, previous: list[str] = (), notes: str = "", vocab: list[str] = (),
             frames: list[bytes] = ()) -> Result:
    result = Result(line=None)
    feedback = None
    for _ in range(2):  # the first draft, then one rewrite
        draft = write_line(features, previous, notes, vocab, frames, feedback)
        if draft is None:
            result.attempts.append({"draft": None, "passed": True, "reason": "writer chose silence"})
            return result
        verdict = check(draft, features)
        result.attempts.append({"draft": draft, "passed": verdict.passed, "reason": verdict.reason})
        if verdict.passed:
            result.line = draft
            return result
        feedback = verdict.reason
    return result  # rejected twice: stay silent


def main():
    samples = json.loads(Path(sys.argv[1]).read_text())
    previous = []
    for sample in samples:
        start = time.perf_counter()
        result = describe(sample["features"], previous, vocab=sample.get("vocab", []))
        took = time.perf_counter() - start
        print(f"[{sample['label']}] {took:.1f}s  ->  {result.line or '(silent)'}")
        for attempt in result.attempts:
            if not attempt["passed"]:
                print(f"    rejected: \"{attempt['draft']}\" ({attempt['reason']})")
        if result.line:
            previous.append(result.line)


if __name__ == "__main__":
    main()
