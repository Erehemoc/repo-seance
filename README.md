# repo-séance

**Summon the ghost of an abandoned open-source project from its git history. Offline, with Gemma.**

![demo](demo/demo.gif)

Every abandoned repository is a small grave. Its history is still all there: who wrote the first line, who carried it for years, the last thing anyone said before it went quiet. `repo-séance` reads that history and lets you talk to what is left.

- **`epitaph`** carves a tombstone from `git log`: born, last words, lifespan, how long it has been silent, the people who kept it alive. Then Gemma writes four lines of verse for it.
- **`ask`** lets you question the ghost. It answers in the first person, and **every sentence has to cite a real commit**.

```bash
git clone https://github.com/left-pad/left-pad
python seance.py epitaph left-pad
python seance.py ask left-pad "Why did you change hands in 2016?"
```

## A ghost that cannot lie about its own life

A model asked about a project's past will happily invent one. The séance has rules:

1. **The tombstone is not written by the model.** Dates, counts, last words and keepers are computed from git in Python. Gemma only writes the verse, and any number in the verse must be one of the facts it was given. If it writes "thirteen winters" for a five-year life, the verse is thrown away and asked for again.
2. **The ghost only sees a few memories.** For each question, a small BM25 search picks about six commits (message, changed files, a slice of the diff, author, date). Gemma answers from those and nothing else.
3. **Citations are checked.** A citation to a commit the ghost was not shown is struck out (`[~~1234567~~ not in my memories]`).
4. **Citations are also checked for meaning.** If a claim cites a real commit whose words do not back it up, or names someone who did not write that commit, it gets a ⚠.
5. **No citation, no answer.** If the ghost cannot point to a single commit, or only says it does not remember, the reply is *"The spirits are silent"*, followed by the closest commits so you can look yourself.

Every answer ends with the evidence: the cited commits with their dates, authors and messages.

## Real runs (Gemma 3 4B, 2 CPU cores, no network)

On `left-pad`, the tiny npm package whose removal in March 2016 broke builds across the JavaScript world:

```
╭──────────────────────────────────────────────────────────────────────────────────────────────────╮
│  HERE LIES LEFT-PAD                                                                              │
│  born 2014-03-14 by E.Azer Koçulu: "initial"                                                     │
│  last words 2019-03-15: "Fixes typo in readme" (Alex Jacobs, 6955230)                            │
│  lived 5 years, 0 months · silent for 7 years, 7 months                                          │
│  72 commits by 19 souls · most devoted: Steve Mao (31), E.Azer Koçulu (7), Cameron Westland (7)  │
│  most alive in 2016-09 (15 commits)                                                              │
│  kept by: E.Azer Koçulu (2014) → Steve Mao (2015) → jamie (2018)                                 │
│         → Steve Mao (2019)                                                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯

Five years breathed, a shallow grace,
Nineteen hands touched its fading space.
A readme’s ghost, a final plea,
Seven years lost, eternally.
```

```
🕯  you ask jquery-pjax: How did you make the back button work?

👻 I remember a fix to reset the hash using `window.location.href = hash` [a19d6fe] to resolve a bug where the
   back button failed after navigating with a hash [a19d6fe] and I also added a loading event when hitting the
   back button [4bfa2fa] to ensure proper behavior. I also had to prevent browser caching of pjax responses
   [75bd2d6] to avoid the back button issue.

📜 evidence:
   75bd2d6  2011-04-04  Chris Wanstrath: Don't browser cache pjax responses (back button bug)
   a19d6fe  2011-07-07  Markus Kaiserswerth: Fix a bug that caused the back button to fail working after navigating to a URL containing a hash
   4bfa2fa  2011-02-28  Chris Wanstrath: fire loading event when you hit the back button too
```

All of that checks out: `a19d6fe` replaces `window.location.hash = hash` with `window.location.href = hash`, and `4bfa2fa` binds a `loading.pjax` event.

```
🕯  you ask left-pad: Why did you change hands in 2016?

👻 I was initially created in 2014 with a simple core [2d60a7f] ⚠, and then Cameron Westland took over in 2016 to
   establish a proper repository [c2222c6], followed by updates to the maintainers [b1f166e], and later, Steve Mao
   released several versions [3c57643], [7898e33], [aff6d74].

   ⚠ 1 claim(s) cite a commit that does not clearly say that: check the evidence
```

The ⚠ is right: the first commit's message is just `initial`, so "a simple core" is the ghost embellishing.

```
🕯  you ask left-pad: What was your favourite food?

👻 The spirits are silent: nothing in my history speaks to that.
```

All transcripts are in [`demo/`](demo), including the one where the checks miss a mistake (see Limits).

## Run it

```bash
pip install -r requirements.txt     # llama-cpp-python
python fetch_model.py               # Gemma 3 4B GGUF, ~2.5 GB, one time (or: python fetch_model.py 1b)
python seance.py epitaph path/to/repo          # add --no-verse for facts only, no model
python seance.py ask path/to/repo "your question" [-k 6]
python -m pytest -q                 # 13 tests, no model needed
```

A question takes about a minute on two CPU cores, and less on a laptop. Nothing leaves your machine: no API key and no network after the model download.

## Limits

- The ghost knows only what commit messages and diff excerpts say. If a project died because of a blog post, an npm drama or a burnt-out maintainer, the repository usually does not record it, and the ghost will (correctly) not remember.
- Retrieval is keyword-based with a small synonym list ("change hands" → maintainers, publishing). A question phrased far from the commits' words may come back silent.
- The ⚠ check is lexical, plus a check that a named person actually wrote the cited commit. It catches a claim pinned to the wrong commit or the wrong person, but not a claim that gets the direction of a change wrong. In [`demo/ask-license.txt`](demo/ask-license.txt) the ghost says the old COPYING file was deleted "in favor of the WTFPL" [6d35dfb]. In fact that commit removed the WTFPL text so an MIT LICENSE could replace it, and nothing flagged the claim. That is why every answer prints its evidence.
- Only the default branch is read. Bots bumping dependencies on side branches are not signs of life.

Gemma is used under the [Gemma Terms of Use](https://ai.google.dev/gemma/terms). Code is MIT licensed. Built with AI assistance (Claude).
