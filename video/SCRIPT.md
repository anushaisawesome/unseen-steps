# Demo video script (3:00, voice-over by Anusha and Andrii)

Built from Andrii's draft (SPEC 10). Record each numbered part as its own file (a phone voice memo is fine; quiet
room, phone 20 cm away), named `1-hook.m4a`, `2-now.m4a`, ... and drop them in `video/voice/`. Read naturally, not fast;
pauses are fine, I cut them. About 320 spoken words, so roughly 2:10 of talking plus the live narration and music.

| # | Who | On screen | Say |
| --- | --- | --- | --- |
| 1 | Anusha | Black, then a blurred dance, music only (10 s) | "Close your eyes." |
| 2 | Andrii | Still blurred; Gemini Live's narration plays (20 s) | "What about now?" |
| 3 | Anusha | The blur clears: Andrii dancing, skeleton, captions | "You noticed the difference. The first time, you heard what a blind or partially sighted person often gets at a dance show: the music, and nothing of the dance. The second time, you heard Unseen Steps describing Andrii live, in the gaps in the music." |
| 4 | Andrii | His own dancing | "Back in Ukraine, I did ballroom dancing for five years, and it was a big part of my childhood. So I know what's behind every dance: the steps, the timing, the grace, all the little details that make a performance what it is." |
| 5 | Anusha | The studio recital print, a studio show | "My tutor, Gerard, works with blind dancers. He told me how often, even though they hear the music, they miss what's actually happening on stage. Andrii brought the dance, I brought the accessibility problem, and together we built Unseen Steps." |
| 6 | Andrii | What Argon prepared from his rehearsal (real show notes from Atlas) | "Before the show, Gemini 4 Argon watches the rehearsal with its music, all in one go. It works out the structure, the key moments and what each movement means, not just where someone's arms and legs are. Then it writes show notes the studio can read and edit, stored in MongoDB Atlas." |
| 7 | Anusha | Andrii live, the under-the-hood panel, the checker catching a wrong line | "During the show, pose tracking follows the dancer, and Gemini Live, holding those notes, describes what's actually happening, in the gaps in the music, in under a second. Every claim is checked against the measured movement. Here it said right when he travelled left, and the next line put it right." |
| 8 | (no voice) | A 20-dancer crew, every dancer tracked; its own narration plays | |
| 9 | Andrii | The crowded competition waltz (everyone else blurred), then the 18 styles page | "And it isn't just one dancer. It follows a whole crew, or one couple in a crowded competition, with everyone else blurred for privacy. And it works across eighteen styles so far, from ballet to Bharatanatyam, each in its own vocabulary." |
| 10 | Anusha | The site, then the end card | "Small studios, schools and competitions are where most people dance, and their shows never get audio description. Unseen Steps is open source, so any studio can use it, and next we're testing it with Gerard's dancers. So that everyone in the audience can experience the dance, not just the music." |

Notes on the changes from the draft:
- Part 3: "how blind people experience performances" became "what a blind or partially sighted person often gets",
  since sight loss varies and most people keep some sight; the blur is an illustration, not a simulation.
- Part 6: added "the studio can read and edit" (people stay in control, a DeepMind criterion) and MongoDB Atlas (the
  MongoDB bounty asks to see it in use).
- Part 7: names the checker catch that's on screen (the verification loop, DeepMind's 50%).
- Part 9: privacy and messy inputs (The Real World's criteria).
- Part 10: open source and the next step with Gerard's dancers (DeepMind: "could it grow into a product or
  open-source tool").
