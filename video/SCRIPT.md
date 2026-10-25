# Demo video script (final, for recording)

Andrii's transcript (SPEC.md) with light fixes. 🟣 = Anusha, 🔵 = Andrii. Record each numbered part as its own phone
voice memo, named by its number (`1.m4a`, `2.m4a`, ... `15.m4a`), and put them in `video/voice/` (or send them over).
Quiet room, phone about 20 cm away, read naturally; I trim the pauses. The edit fits itself to your timing.

| # | Who | On screen | Say |
| --- | --- | --- | --- |
| 1 | 🟣 | Blurred dance, music only (10 s) | "Close your eyes." |
| 2 | 🟣 | Still blurred; the live narration plays with subtitles | "What about now?" |
| 3 | 🟣 | The blur clears: Andrii dancing, skeleton, captions | "You noticed the difference, right? The first clip is what a blind or partially sighted person often gets at a dance show: the music, and nothing of the dance. The second is our answer: dance you can hear." |
| 4 | 🔵 | Andrii's own dancing | "Back in Ukraine, I did ballroom dancing for five years, and it was a big part of my childhood. So I know everything behind each dance: the steps, the timing, the grace, all the little details that make a performance what it is." |
| 5 | 🟣 | The studio recital print | "There are over two million people in the UK with sight loss. My tutor, Gerard, works with blind dancers. He told me how often, even though they hear the music, they miss what's actually happening on stage." |
| 6 | 🔵 | The recital print | "That's how we came up with the idea. I brought the dance experience, and Anusha brought the accessibility problem." |
| 7 | 🟣 | The recital print, then the site | "And my own training, commercial, contemporary and ballet growing up, and street styles now, shaped how it describes every style. So, we built Unseen Steps." |
| 8 | 🔵 | Andrii dancing live, then Argon's show notes from his rehearsal | "Before the performance, Gemini 4 Argon watches the rehearsal with its music, at five to eight frames a second, all in one go. It works out the structure, the key moments and what each movement means, not just where someone's arms or legs are. The studio can read and edit these show notes." |
| 9 | 🟣 | Andrii live with the under-the-hood panel | "During the performance, YOLO pose tracking follows the dancer, while Gemini Live describes what's happening in under a second, even if the dancer changes something from rehearsal." |
| 10 | 🔵 | The checker catching a wrong line | "But we didn't want the AI to just guess. If the body tracking doesn't support a turn, a direction or a jump, our checker flags it, and the next line puts it right." |
| 11 | 🟣 | The glossary and shows in MongoDB Atlas | "Dance, like code, has its own language. With Deep Research and MongoDB Atlas, we built a glossary of terms reviewed by dancers, with professional and simpler names, and every show's notes live there too." |
| 12 | (no voice) | A 20-dancer crew, every dancer tracked; 18 styles | |
| 13 | 🔵 | Andrii dancing | "For me, dance is five years of my childhood." |
| 14 | 🟣 | The recital print | "For the people Gerard works with, this could mean getting the whole performance, not just the music. And it's open source, so any studio can use it." |
| 15 | 🔵🟣 together | End card | "That's what we want Unseen Steps to do." |

What changed from the transcript, and why:
- 3: "how blind people experience performances" became "what a blind or partially sighted person often gets": sight loss
  varies, and most people keep some sight. "Such life unfairness" became "our answer: dance you can hear".
- 5: "There is over 2 million people" became "There are over two million people in the UK with sight loss" (RNIB).
- 7: Anusha's dance training, and "So, we built Unseen Steps".
- 8: "the studio can read and edit these show notes" (DeepMind scores people staying in control).
- 10: the checker flags a line live and the next line corrects it; the studio editing the notes is in part 8.
- 11: "and every show's notes live there too" so the MongoDB judges hear Atlas holds the shows, not just the glossary.
- 14: open source (DeepMind asks whether it could become an open-source tool people use).
