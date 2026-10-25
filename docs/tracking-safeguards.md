# When body tracking goes wrong

There's no single "tracking is wrong" check. Each layer of the pipeline assumes the one below can fail, and the rule
throughout is: **if tracking is unsure, measure nothing and say less; never guess a jump, turn or direction that
wasn't measured.**

| Layer | What it does | Where |
| --- | --- | --- |
| 1. Pose confidence, per frame | A person is kept only at detection confidence >= 0.3; live follows the biggest, clearest person (box size × keypoint confidence). Keypoints under 0.3 are left out of measurements; legs and turnout only when hips, knees and ankles are clearly visible (> 0.5; long dresses hide ankles). Only keypoints > 0.5 are drawn, so a backlit frame gets no skeleton instead of wrong legs. | `scripts/live.py` `track`, `scripts/killtest.py` |
| 2. Coverage, per phrase | If the dancer was tracked in under 30% of a phrase's frames, the phrase is `tracking: "poor"` and nothing is measured. The checker then rejects body claims ("leaps high", "turns to his right", "travels left", "kneels") and lets plain wording through ("gliding gracefully through the waltz"). | `killtest.phrase_features`, `server/checker.py` |
| 3. Unmeasurable = unchecked | A measurement that can't be made (rotation in profile, jumps or turns in a group) is `None`, and its claims are skipped rather than guessed. With two dancers, a line about one of them ("he", "she") is rejected unless tracking tells them apart. | `server/checker.py` |
| 4. Crowded footage | A marked couple is followed by dress colour, single-frame jumps are capped and skeletons smoothed. If they're lost, it goes silent and only re-acquires when pose and clothing both match: it would rather say nothing than describe the wrong couple. | `killtest.track_focus` |
| 5. Gemini sees the camera too | Live, Gemini gets the frames themselves (2 a second), not only pose numbers. Pose is sent as "a check only: don't contradict them, don't narrate them", so a bad reading doesn't become the narration. A flagged line is reported in the next prompt and the next line puts it right. | `scripts/live.py` |
| 6. People can see it | `scripts/track_debug.py` makes a contact sheet of who was followed (pink) before rendering; the on-screen skeleton shows the audience what was tracked. | `scripts/track_debug.py` |

**Not built (don't claim):** Robotics-ER spot-checks that the tracker is still on the right dancer (planned only).

**Known flaw:** when tracking is poor, the checker's rejection reasons are misleading ("the dancer stayed standing"
when really nothing was measured). The verdict is right; the wording should say "not measured".

**One line for the pitch or video:** "If tracking is unsure, it measures nothing and says less. It never guesses a jump,
turn or direction it couldn't measure."
