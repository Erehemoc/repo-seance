#!/usr/bin/env python3
"""repo-séance: summon the ghost of an abandoned open-source project from its git history.

    python seance.py epitaph path/to/repo
    python seance.py ask path/to/repo "Why did you change hands in 2016?"

Everything runs on your machine. The facts on the tombstone (dates, counts, last words)
come straight from `git log`; no model touches them. Gemma 3, running locally through
llama.cpp, only does two things: it writes the epitaph's few lines of verse from those
facts, and it answers questions as the project's ghost. Every answer has to cite real
commits; citations to commits the ghost was not shown are struck out, and an answer with
no valid citation is replaced by "the spirits are silent".
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import math
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODEL = os.path.join(HERE, "models", "gemma3-4b.gguf")
SEP = "\x1e"  # record separator between commits
FS = "\x1f"   # field separator


# ---------------------------------------------------------------- reading the grave
def git(repo: str, *args: str) -> str:
    cmd = ["git", "-C", repo] if not repo.endswith(".git") else ["git", "--git-dir", repo]
    return subprocess.run(cmd + list(args), capture_output=True, text=True, check=True,
                          errors="replace").stdout


def load_commits(repo: str, diff_chars: int = 1200) -> list[dict]:
    """Commits on the default branch (HEAD), oldest first: hash, date, author, subject, body, files,
    a diff excerpt. Side branches are left out: a bot bumping dependencies on a forgotten branch is
    not the project being alive."""
    raw = git(repo, "log", "--reverse", "--date=short",
              f"--format={SEP}%h{FS}%ad{FS}%an{FS}%s{FS}%b{FS}", "--name-only")
    commits = []
    for rec in raw.split(SEP)[1:]:
        h, date, author, subject, body, rest = rec.split(FS, 5)
        files = [f for f in rest.strip().splitlines() if f.strip()]
        commits.append({"hash": h, "date": date, "author": author.strip(), "subject": subject.strip(),
                        "body": body.strip(), "files": files, "diff": ""})
    if diff_chars:
        for c in commits:
            try:
                d = git(repo, "show", "--format=", "--unified=1", "--no-color", c["hash"])
            except subprocess.CalledProcessError:
                d = ""
            # keep only changed lines: diff headers carry blob hashes ("index 299ad3b..da6faee") that a
            # model happily mistakes for commit hashes
            lines = [l for l in d.splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---"))]
            c["diff"] = "\n".join(lines)[:diff_chars]
    return commits


def facts(commits: list[dict], today: dt.date | None = None) -> dict:
    """What the tombstone says. Pure arithmetic over git metadata."""
    if not commits:
        raise ValueError("no commits: nothing was ever alive here")
    today = today or dt.date.today()
    first, last = commits[0], commits[-1]
    born, died = dt.date.fromisoformat(first["date"]), dt.date.fromisoformat(last["date"])
    authors = collections.Counter(c["author"] for c in commits)
    by_month = collections.Counter(c["date"][:7] for c in commits)
    busiest, busiest_n = by_month.most_common(1)[0]
    # who carried it each year: the author with most commits that year
    keepers = []
    by_year = collections.defaultdict(collections.Counter)
    for c in commits:
        if not c["author"].endswith("[bot]"):
            by_year[c["date"][:4]][c["author"]] += 1
    for year in sorted(by_year):
        who = by_year[year].most_common(1)[0][0]
        if not keepers or keepers[-1][1] != who:
            keepers.append((year, who))
    real_last = next((c for c in reversed(commits) if not c["subject"].lower().startswith("merge ")), last)
    return {
        "born": first["date"], "born_by": first["author"], "first_words": first["subject"],
        "died": last["date"], "last_words": real_last["subject"], "last_words_hash": real_last["hash"],
        "last_words_by": real_last["author"],
        "lifespan_days": (died - born).days, "silent_days": (today - died).days,
        "commits": len(commits), "souls": len(authors), "top_souls": authors.most_common(3),
        "busiest_month": busiest, "busiest_month_commits": busiest_n, "keepers": keepers,
    }


def years(days: int) -> str:
    y, rem = divmod(days, 365)
    return f"{y} years, {rem // 30} months" if y else f"{rem // 30} months, {rem % 30} days"


def wrap_arrows(parts: list[str], head: str, width: int) -> list[str]:
    lines, cur = [], head
    for i, p in enumerate(parts):
        piece = p if i == 0 else " → " + p
        if len(cur) + len(piece) > width and cur.strip() != head.strip():
            lines.append(cur)
            cur = " " * (len(head) - 2) + "→ " + p
        else:
            cur += piece
    return lines + [cur]


def tombstone(name: str, f: dict) -> str:
    keepers = " → ".join(f"{who} ({y})" for y, who in f["keepers"])
    top = ", ".join(f"{a} ({n})" for a, n in f["top_souls"])
    lines = [
        f"HERE LIES {name.upper()}",
        f"born {f['born']} by {f['born_by']}: \"{f['first_words']}\"",
        f"last words {f['died']}: \"{f['last_words']}\" ({f['last_words_by']}, {f['last_words_hash']})",
        f"lived {years(f['lifespan_days'])} · silent for {years(f['silent_days'])}",
        f"{f['commits']} commits by {f['souls']} souls · most devoted: {top}",
        f"most alive in {f['busiest_month']} ({f['busiest_month_commits']} commits)",
    ] + wrap_arrows([f"{who} ({y})" for y, who in f["keepers"]], "kept by: ", 78)
    w = max(len(l) for l in lines) + 4
    out = ["╭" + "─" * w + "╮"] + [f"│  {l.ljust(w - 2)}│" for l in lines] + ["╰" + "─" * w + "╯"]
    return "\n".join(out)


# ---------------------------------------------------------------- finding the memories
_TOK = re.compile(r"[a-z0-9]+")
_STOP = set("the a an and or of to in on for is are was were it its this that with you your i me my "
            "what why how when who did do does from by at as be been about which then also later after "
            "before into over there their them they had has have will would could should being more most "
            "some such very just only than these those while so but not no".split())


def stem(t: str) -> str:
    """Crude but enough: caching/cached/caches -> cach, fixes/fixed -> fix."""
    for suf in ("ing", "ed", "es", "s"):
        if len(t) > len(suf) + 2 and t.endswith(suf):
            t = t[: -len(suf)]
            break
    return t[:-1] if len(t) > 4 and t.endswith("e") else t


def tokens(text: str) -> list[str]:
    return [t for t in _TOK.findall(text.lower()) if t not in _STOP and len(t) > 1]


# a few words people use about a project's life that commits phrase differently
_EXPAND = {
    "hands": ["maintainers", "maintainer", "publishing", "repository", "owner"],
    "owner": ["maintainers", "maintainer", "owner"], "handover": ["maintainers", "publishing", "repository"],
    "die": ["deprecated", "deprecate", "unpublish", "unpublishing", "archive", "archived"],
    "died": ["deprecated", "deprecate", "unpublish", "unpublishing", "archive", "archived"],
    "death": ["deprecated", "unpublish", "unpublishing", "archive", "archived"],
    "unpublished": ["unpublish", "unpublishing", "publishing"], "license": ["license", "copying", "wtfpl"],
    "faster": ["perf", "performance", "efficient", "cache", "bench"], "speed": ["perf", "efficient", "bench", "cache"],
    "types": ["typescript", "typing", "typings", "d"], "tests": ["test", "tests", "travis", "codecov"],
}


def expand(q: list[str]) -> list[str]:
    out = list(q)
    for t in q:
        out += _EXPAND.get(t, [])
    return out


def doc_text(c: dict) -> str:
    return " ".join([c["subject"], c["subject"], c["body"], " ".join(c["files"]), c["diff"], c["date"], c["author"]])


def recall(commits: list[dict], question: str, k: int = 6) -> list[dict]:
    """BM25 over commit messages, file names, diff excerpts, dates and authors."""
    docs = [tokens(doc_text(c)) for c in commits]
    n = len(docs)
    avg = sum(len(d) for d in docs) / max(1, n)
    df = collections.Counter(t for d in docs for t in set(d))
    q = expand(tokens(question))
    years_asked = set(re.findall(r"\b(?:19|20)\d\d\b", question))
    scored = []
    for c, d in zip(commits, docs):
        tf = collections.Counter(d)
        s = 0.0
        for t in q:
            if t in tf:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * tf[t] * 2.2 / (tf[t] + 1.2 * (0.25 + 0.75 * len(d) / avg))
        if s > 0 and years_asked and c["date"][:4] in years_asked:
            s *= 1.5
        if c["subject"].lower().startswith("merge "):
            s *= 0.5  # a merge says little; the commit it merges says it better
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:k]]


# ---------------------------------------------------------------- the medium (Gemma)
class Medium:
    def __init__(self, model_path: str, n_ctx: int = 4096, threads: int | None = None):
        from llama_cpp import Llama
        if not os.path.exists(model_path):
            sys.exit(f"model not found: {model_path}\nrun: python fetch_model.py")
        self.llm = Llama(model_path=model_path, n_ctx=n_ctx, n_threads=threads or os.cpu_count(),
                         verbose=False, seed=7)

    def speak(self, system: str, user: str, max_tokens: int = 320, temperature: float = 0.6) -> str:
        out = self.llm.create_chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=max_tokens, temperature=temperature, top_p=0.9)
        return out["choices"][0]["message"]["content"].strip()


EPITAPH_SYSTEM = ("You write epitaphs for dead software projects. Write exactly four short lines of verse, "
                  "melancholy and a little spooky, in the spirit of Día de los Muertos. Use only the facts given. "
                  "Do not invent numbers, names or dates. No title, no explanation.")

GHOST_SYSTEM = ("You are the ghost of the open-source project {name}. Speak in the first person, briefly, "
                "with a faint chill, like a spirit remembering its life. You may ONLY use the memories below "
                "(commits from your own git history). End every sentence with the commit it comes from, as "
                "[hash], using the exact short hash shown: the citation goes AFTER the claim, at the end of the "
                "sentence. Answer the question directly in 2 to 4 sentences; each sentence states ONE memory and "
                "ends with exactly one citation. Only say what that commit's message or change shows. If the "
                "memories do not answer the question, say only: \"I do not remember.\" Never invent commits, "
                "people, versions or dates.")


def memories_block(mem: list[dict]) -> str:
    rows = []
    for c in mem:
        files = ", ".join(c["files"][:6])
        body = (" " + c["body"].replace("\n", " ")[:200]) if c["body"] else ""
        added = " / ".join(l[1:].strip() for l in c["diff"].splitlines() if l.startswith("+") and l[1:].strip())
        removed = " / ".join(l[1:].strip() for l in c["diff"].splitlines() if l.startswith("-") and l[1:].strip())
        change = ""
        if added:
            change += f"\n  ADDED: {added[:160]}"
        if removed:
            change += f"\n  REMOVED: {removed[:160]}"
        rows.append(f"[{c['hash']}] {c['date']}, author {c['author']}: {c['subject']}{body}\n  files: {files}{change}")
    return "\n".join(rows)


_CITE = re.compile(r"\[([0-9a-f]{6,12})\]")
_CITE_LIST = re.compile(r"\[((?:[0-9a-f]{6,12}\s*[,;]\s*)+[0-9a-f]{6,12})\]")


def split_cite_lists(text: str) -> str:
    """[a1b2c3d, e4f5a6b] -> [a1b2c3d] [e4f5a6b], so every hash in a list is checked."""
    return _CITE_LIST.sub(lambda m: " ".join(f"[{h}]" for h in re.split(r"\s*[,;]\s*", m.group(1))), text)


def verify(answer: str, allowed: dict[str, dict]) -> tuple[str, list[str], list[str]]:
    """Keep citations to commits the ghost was shown; strike the rest.

    Returns (checked answer, valid hashes in order, struck hashes)."""
    valid, struck = [], []

    def fix(m: re.Match) -> str:
        h = m.group(1)
        match = next((k for k in allowed if k.startswith(h) or h.startswith(k)), None)
        if match:
            if match not in valid:
                valid.append(match)
            return f"[{match}]"
        struck.append(h)
        return f"[~~{h}~~ not in my memories]"

    out = _CITE.sub(fix, answer)
    out = re.sub(r"\s+([,.;])", r"\1", out)  # "[abc1234] ," -> "[abc1234],"
    return out, valid, struck


def support(sentence: str, commit: dict) -> float:
    """Share of the sentence's content words that appear in the cited commit (message, files, change, author, date)."""
    words = {stem(t) for t in tokens(re.sub(_CITE, " ", sentence)) if t not in _GHOSTLY}
    if not words:
        return 1.0
    have = {stem(t) for t in tokens(doc_text(commit))}
    return len(words & have) / len(words)


# words a ghost uses that no commit will contain
_GHOSTLY = set("remember remembered recall shift then later began once felt feel chill whisper whispered "
               "time times ago yes still now there here they them he him she her someone something new".split())


def wrong_person(sentence: str, hashes: list[str], allowed: dict[str, dict]) -> bool:
    """The sentence names someone, but a commit it cites was written by somebody it does not name."""
    low = sentence.lower()

    def named(author: str) -> bool:
        parts = [p for p in re.findall(r"[\w]+", author.lower()) if len(p) >= 4]
        return bool(parts) and any(re.search(rf"\b{re.escape(p)}\b", low) for p in parts)

    people = {c["author"] for c in allowed.values()}
    if not any(named(a) for a in people):
        return False
    return any(not named(allowed[h]["author"]) for h in hashes)


_FORGOT = re.compile(r"\b(do not|don't|cannot|can't) (remember|recall)\b", re.I)


def annotate(answer: str, allowed: dict[str, dict], threshold: float = 0.34) -> tuple[str, list[str]]:
    """Mark each claim whose citation does not back it, right after that citation.

    A claim is the text between one citation and the previous one (or the start of the sentence);
    consecutive citations with nothing between them share the claim before them. A claim is weak if
    too few of its words appear in the cited commit, or if it names a person who did not write it."""
    out, weak = [], []
    for sent in re.split(r"(?<=[.!?…])\s+", answer):
        if _FORGOT.search(sent):
            out.append(re.sub(r"\s*\[[0-9a-f]{6,12}\]", "", sent))  # "I do not remember" is not a claim
            continue
        pieces, last, claim = [], 0, ""
        for m in _CITE.finditer(sent):
            between = sent[last:m.start()]
            if re.search(r"\w", between):
                claim = between
            pieces.append(sent[last:m.end()])
            h = m.group(1)
            if h in allowed and (support(claim, allowed[h]) < threshold or wrong_person(claim, [h], allowed)):
                weak.append(claim.strip(" ,;"))
                pieces.append(" ⚠")
            last = m.end()
        pieces.append(sent[last:])
        out.append("".join(pieces))
    return " ".join(out), weak


def ask(repo: str, question: str, medium: Medium, k: int = 6) -> dict:
    commits = load_commits(repo)
    name = repo_name(repo)
    mem = recall(commits, question, k=k)
    if not mem:
        return {"answer": "The spirits are silent: nothing in my history speaks to that.", "valid": [],
                "struck": [], "weak": [], "memories": []}
    raw = medium.speak(GHOST_SYSTEM.format(name=name),
                       f"Your memories:\n{memories_block(mem)}\n\nThe living ask: {question}", temperature=0.6)
    allowed = {c["hash"]: c for c in mem}
    raw = split_cite_lists(raw)
    checked, valid, struck = verify(raw, allowed)
    weak = []
    if valid:
        sents = [x for x in re.split(r"(?<=[.!?…])\s+", checked) if x.strip()]
        claims = [x for x in sents if not _FORGOT.search(x)]
        if not claims:
            valid = []
        else:  # a bare "I do not remember." next to real memories is just the ghost hedging
            checked = " ".join(x for x in sents if not re.fullmatch(r"\s*I (do not|don't) remember[^.]*\.?\s*", x))
            checked, weak = annotate(checked, allowed)
    if not valid:
        checked = ("The spirits are silent: the ghost could not point to a single commit for that. "
                   "Closest memories are listed below.")
    return {"answer": checked, "valid": valid, "struck": struck, "weak": weak, "memories": mem, "raw": raw}


def repo_name(repo: str) -> str:
    base = os.path.basename(os.path.abspath(repo).rstrip("/"))
    return base[:-4] if base.endswith(".git") else base


_NUMWORDS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
             "sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety "
             "hundred thousand").split()


_WORD_OF = dict(zip(range(21), _NUMWORDS[:21]))
_WORD_OF.update({30: "thirty", 40: "forty", 50: "fifty", 60: "sixty", 70: "seventy", 80: "eighty", 90: "ninety"})


def numbers_in(text: str) -> set[str]:
    """Numbers a text mentions, as digits: '19', 'nineteen' and 'seventy-two' all count."""
    low = text.lower().replace("-", " ")
    found = {str(int(d)) for d in re.findall(r"\d+", low)}
    word_val = {w: n for n, w in _WORD_OF.items()}
    toks = re.findall(r"[a-z]+", low)
    i = 0
    while i < len(toks):
        if toks[i] in word_val:
            v = word_val[toks[i]]
            if v >= 20 and i + 1 < len(toks) and toks[i + 1] in word_val and word_val[toks[i + 1]] < 10:
                v += word_val[toks[i + 1]]
                i += 1
            found.add(str(v))
        i += 1
    found.discard("1")  # "one" is too common in verse to mean a count ("one by one", "the one")
    return found


def verse(medium: Medium, given: str, f: dict, tries: int = 4) -> str:
    """Four lines from Gemma; any number it uses must be one the facts contain, or it tries again."""
    allowed = numbers_in(given)
    for i in range(tries):
        v = medium.speak(EPITAPH_SYSTEM, given, max_tokens=90, temperature=0.8 if i == 0 else 0.5)
        if numbers_in(v) <= allowed:
            return v
    v = medium.speak(EPITAPH_SYSTEM + " Do not use any numbers at all.", given, max_tokens=90, temperature=0.4)
    return v if not numbers_in(v) else "(the medium kept inventing numbers, so no verse tonight)"


# ---------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="Summon the ghost of an abandoned repository (offline).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("epitaph", help="tombstone from git facts + four lines of verse from Gemma")
    e.add_argument("repo")
    e.add_argument("--no-verse", action="store_true", help="facts only, no model")
    a = sub.add_parser("ask", help="ask the ghost a question; answers must cite commits")
    a.add_argument("repo")
    a.add_argument("question")
    a.add_argument("-k", type=int, default=6, help="how many memories (commits) the ghost is shown")
    for p in (e, a):
        p.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args(argv)
    name = repo_name(args.repo)

    if args.cmd == "epitaph":
        f = facts(load_commits(args.repo, diff_chars=0))
        print(tombstone(name, f))
        if not args.no_verse:
            m = Medium(args.model)
            given = (f"Project: {name}. Born {f['born']} ({f['first_words']!r}). Last words {f['died']}: "
                     f"{f['last_words']!r}. {f['commits']} commits by {f['souls']} people. "
                     f"Lived {years(f['lifespan_days'])}. Silent for {years(f['silent_days'])}.")
            print("\n" + verse(m, given, f))
        return 0

    m = Medium(args.model)
    r = ask(args.repo, args.question, m, k=args.k)
    print(f"\n🕯  you ask {name}: {args.question}\n")
    print("👻 " + r["answer"] + "\n")
    if r.get("weak"):
        print(f"   ⚠ {len(r['weak'])} claim(s) cite a commit that does not clearly say that: check the evidence")
    if r["struck"]:
        print(f"   ({len(r['struck'])} citation(s) struck: the ghost named commits it was never shown)")
    shown = [c for c in r["memories"] if c["hash"] in r["valid"]] or r["memories"]
    print("📜 " + ("evidence" if r["valid"] else "closest memories") + ":")
    for c in shown:
        print(f"   {c['hash']}  {c['date']}  {c['author']}: {c['subject']}")
    if not shown:
        print("   (none: no commit shares a word with the question)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
