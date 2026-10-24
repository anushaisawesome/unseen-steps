# Feedback on narration

Anusha and Nastia tune the describer by watching renders and writing down what a dancer would have said.

1. Pick a clip (your own footage, a teammate's, free stock such as Mixkit or Pexels; see "Finding clips" in
   `CLAUDE.md`). Put it in `clips/` (gitignored). Share raw clips through the private clips repo, never this one.
2. Render: `python scripts/killtest.py clips/<clip>.mp4 --bars-per-phrase 2 --script`
   (waltz and other 3/4 music: add `--beats-per-bar 3`; ballroom with the glossary: `--style waltz --terms professional`).
3. Watch `data/killtest/<clip>-script-annotated.mp4` with `data/killtest/<clip>-script-review.md` open, and fill in
   the review: the overall box first, then any line that's wrong, late, too long, missing a term, or flat.
   Say what you'd have said instead; that's the most useful part.
4. Save it here as `feedback/<clip>-<your name>.md`, commit and push.

The review header records the brief version (a hash of the describer instructions), so feedback stays tied to
the version it was about. Changes to the describer instructions (`server/scriptwriter.py`) come from this folder;
one person edits them at a time (see `CLAUDE.md`).
