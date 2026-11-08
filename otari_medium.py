"""Hold the séance through Otari (https://otari.ai), Mozilla.ai's open-source AI gateway.

Two things come from Otari:

- OtariMedium: the voice of the ghost. Any model your Otari workspace serves (an open-weight
  one by default), or a routing policy with a fallback. Each answer records which provider and
  model actually spoke, and whether a fallback stepped in.
- rumours(): what the living say about a project, from Otari's search API. Git rarely records
  why a project died (an npm dispute, a blog post, a burnt-out maintainer), so the ghost may now
  repeat rumours from the web. Every rumour must cite a search result by its [rN] tag, and is
  checked and printed apart from the ghost's own memories, with the source URL.

Standard library only: Otari speaks the OpenAI API, so a JSON POST is all it takes.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

BASE_URL = os.environ.get("OTARI_BASE_URL", "https://api.otari.ai/api")
DEFAULT_MODEL = os.environ.get("OTARI_MODEL", "seance")  # a routing policy you create on otari.ai


def api_key(key_file: str | None = None) -> str:
    """OTARI_API_KEY, or the first line of a key file. Never printed."""
    if os.environ.get("OTARI_API_KEY"):
        return os.environ["OTARI_API_KEY"].strip()
    for path in [key_file, "otari_key.txt"]:
        if path and os.path.exists(path):
            return open(path, encoding="utf-8").read().strip().splitlines()[0].strip()
    raise SystemExit("no Otari key: set OTARI_API_KEY or put it in otari_key.txt (never commit it)")


class OtariError(RuntimeError):
    pass


def _post(path: str, body: dict, key: str, base_url: str = BASE_URL, timeout: int = 120):
    req = urllib.request.Request(base_url.rstrip("/") + "/v1" + path, data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "User-Agent": "repo-seance"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode()), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        code = e.headers.get("Otari-Error-Code", "") if e.headers else ""
        try:
            detail = json.loads(e.read().decode()).get("detail", "")
        except Exception:
            detail = ""
        raise OtariError(f"Otari answered {e.code} {code} {detail}".strip()) from None


class OtariMedium:
    """Same interface as seance.Medium (speak), but the voice comes through Otari."""

    def __init__(self, model: str = DEFAULT_MODEL, key: str | None = None, base_url: str = BASE_URL,
                 post=_post):
        self.model, self.key, self.base_url, self._post = model, key or api_key(), base_url, post
        self.last: dict = {}

    def speak(self, system: str, user: str, max_tokens: int = 320, temperature: float = 0.6) -> str:
        body = {"model": self.model, "max_tokens": max_tokens, "temperature": temperature,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        out, headers = self._post("/chat/completions", body, self.key, self.base_url)
        self.last = {"provider": headers.get("otari-provider", "?"),
                     "model": headers.get("otari-model", out.get("model", self.model)),
                     "fallback": headers.get("otari-fallback", "false") == "true",
                     "attempts": headers.get("otari-attempt-count", "1")}
        return (out["choices"][0]["message"].get("content") or "").strip()

    def who(self) -> str:
        if not self.last:
            return ""
        s = f"the medium: {self.last['model']} via {self.last['provider']} on Otari"
        if self.last["fallback"]:
            s += f" (fallback after {int(self.last['attempts']) - 1} failed attempt(s))"
        return s

    def search(self, query: str, max_results: int = 6) -> list[dict]:
        out, _ = self._post("/search", {"query": query, "max_results": max_results,
                                        "max_tokens_per_page": 300}, self.key, self.base_url, timeout=60)
        return [r for r in out.get("results", []) if r.get("url")]


RUMOUR_SYSTEM = ("You are the ghost of the open-source project {name}. Your git history does not answer the "
                 "question, but the living talk. Below are search results about you, each tagged [r1], [r2]... "
                 "Repeat what they say, in the first person, briefly, like a spirit hearing gossip at its grave: "
                 "1 to 3 sentences, each ending with exactly one tag of the result it comes from. Only say what "
                 "that result's text says. If none of them speaks to the question, say only: \"The living say "
                 "nothing of that.\"")

_RTAG = re.compile(r"\[(r\d+)\]")
# words a gossiping ghost uses that no search result needs to contain
_GOSSIP = re.compile(r"\b(living|say|says|said|talk|talks|whisper\w*|rumou?rs?|gossip|hear|heard|they|claim\w*|"
                     r"apparently|people|folks|some)\b", re.I)


def rumour_block(results: list[dict]) -> str:
    return "\n\n".join(f"[r{i}] {r.get('title', '')} ({r['url']})\n{(r.get('snippet') or '')[:900]}"
                       for i, r in enumerate(results, 1))


def check_rumours(text: str, results: list[dict], support) -> dict:
    """Keep rumours that cite a real result; strike tags that point nowhere; ⚠ weakly supported ones."""
    by_tag = {f"r{i}": r for i, r in enumerate(results, 1)}
    struck, cited, weak = [], [], []

    def fix(m):
        t = m.group(1)
        if t in by_tag:
            if t not in cited:
                cited.append(t)
            return f"[{t}]"
        struck.append(t)
        return f"[~~{t}~~ no such rumour]"

    text = _RTAG.sub(fix, text)
    out = []
    for s in [x for x in re.split(r"(?<=[.!?…])\s+", text) if x.strip()]:
        tags = [t for t in _RTAG.findall(s) if t in by_tag]
        if tags:
            r = by_tag[tags[-1]]
            doc = {"subject": r.get("title", ""), "body": r.get("snippet", ""), "files": [], "diff": "",
                   "author": "", "date": r.get("date") or ""}
            if support(_GOSSIP.sub(" ", _RTAG.sub(" ", s)), doc) < 0.34:
                weak.append(s)
                s = s.rstrip() + " ⚠"
        out.append(s)
    return {"text": " ".join(out), "cited": cited, "struck": struck, "weak": weak,
            "sources": [(t, by_tag[t]) for t in cited]}


def rumours(name: str, question: str, medium: OtariMedium, support, extra: str = "") -> dict:
    results = medium.search(f"{name} {extra} {question}".strip())
    if not results:
        return {"text": "The living say nothing of that.", "cited": [], "struck": [], "weak": [], "sources": []}
    raw = medium.speak(RUMOUR_SYSTEM.format(name=name),
                       f"What the living say:\n{rumour_block(results)}\n\nThe question: {question}",
                       max_tokens=260, temperature=0.4)
    r = check_rumours(raw, results, support)
    if not r["cited"]:
        r["text"] = "The living say nothing of that."
    r["raw"] = raw
    return r
