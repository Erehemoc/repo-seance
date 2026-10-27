# repo-séance

**Summon the ghost of an abandoned open-source project from its git history. Offline, with Gemma.**

![demo](demo/demo.gif)

Every abandoned repository is a small grave. Its history is still all there: who wrote the first line, who carried it for years, the last thing anyone said before it went quiet. `repo-séance` reads that history and lets you talk to what is left.

- **`epitaph`** carves a tombstone from `git log`: born, last words, lifespan, how long it has been silent, the people who kept it alive. Then Gemma writes four lines of verse for it.
- **`ask`** lets you question the ghost. It answers in the first person, and **every sentence has to cite a real commit**.

```bash
git clone https://github.com/left-pad/left-pad
python seance.py epitaph left-pad
python seance.py ask left-pad "Who gave you a license, and which one?"
```

## A ghost that cannot lie about its own life

A model asked about a project's past will happily invent one. The séance has rules:

1. **The tombstone is not written by the model.** Dates, counts, last words and keepers are computed from git in Python. Gemma only writes the verse, and any number in the verse must be one of the facts it was given. If it writes "thirteen winters" for a five-year life, the verse is thrown away and asked for again.
2. **The ghost only sees a few memories.** For each question, a small BM25 search picks about six commits (message, changed files, a slice of the diff, author, date). Gemma answers from those and nothing else.
3. **Citations are checked.** A citation to a commit the ghost was not shown is struck out (`[~~1234567~~ not in my memories]`).
4. **Citations are also checked for meaning.** If a sentence cites a real commit whose words do not back it up, the sentence gets a ⚠.
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
🕯  you ask left-pad: Who gave you a license, and which one?

👻 I remember being updated with the MIT license [d81cb1c], and the WTFPL was initially added by cht8687 [5836927].
   I then had the WTFPL replaced by the MIT license by 100Errors [bc08b65]. I was initially using the WTFPL
   license [5836927], and later replaced with a LICENSE file [6d35dfb].

📜 evidence:
   5836927  2016-09-24  cht8687: [Issue20]: Add in WTFPL
   6d35dfb  2018-11-13  jamie: Deleting COPYING; will replace with LICENSE file
   bc08b65  2019-01-06  100Errors: License Update
   d81cb1c  2018-11-13  jamie: Create LICENSE
```

All of that checks out: `bc08b65` changes `"license": "WTFPL"` to `"MIT"` in `package.json`, and `d81cb1c` adds an MIT `LICENSE`.

```
🕯  you ask left-pad: What was your favourite food?

👻 The spirits are silent: nothing in my history speaks to that.
```

All transcripts are in [`demo/`](demo), including one from `jquery-pjax` (*"How did you make the back button work?"*).

## Run it

```bash
pip install -r requirements.txt     # llama-cpp-python
python fetch_model.py               # Gemma 3 4B GGUF, ~2.5 GB, one time (or: python fetch_model.py 1b)
python seance.py epitaph path/to/repo          # add --no-verse for facts only, no model
python seance.py ask path/to/repo "your question" [-k 6]
python -m pytest -q                 # 10 tests, no model needed
```

A question takes about a minute on two CPU cores, and less on a laptop. Nothing leaves your machine: no API key and no network after the model download.

## Limits

- The ghost knows only what commit messages and diff excerpts say. If a project died because of a blog post, an npm drama or a burnt-out maintainer, the repository usually does not record it, and the ghost will (correctly) not remember.
- Retrieval is keyword-based with a small synonym list ("change hands" → maintainers, publishing). A question phrased far from the commits' words may come back silent.
- The ⚠ check is lexical. It catches a sentence that cites the wrong commit, but not a sentence that is subtly overstated.
- Only the default branch is read. Bots bumping dependencies on side branches are not signs of life.

Gemma is used under the [Gemma Terms of Use](https://ai.google.dev/gemma/terms). Code is MIT licensed. Built with AI assistance (Claude).
