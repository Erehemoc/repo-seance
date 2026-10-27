"""Tests for repo-séance. No model is loaded: the ask() path uses a scripted fake medium."""
import datetime as dt
import os
import subprocess

import pytest

import seance


@pytest.fixture()
def grave(tmp_path):
    """A tiny repository with a known life: born, handed over, licensed, then silent."""
    r = tmp_path / "tiny-lib"
    r.mkdir()
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")

    def commit(msg, author, date, fname, text):
        (r / fname).write_text(text)
        subprocess.run(["git", "add", fname], cwd=r, check=True, env=env)
        e = dict(env, GIT_AUTHOR_NAME=author, GIT_AUTHOR_EMAIL="a@x", GIT_COMMITTER_NAME=author,
                 GIT_COMMITTER_EMAIL="a@x", GIT_AUTHOR_DATE=f"{date}T12:00:00", GIT_COMMITTER_DATE=f"{date}T12:00:00")
        subprocess.run(["git", "commit", "-q", "-m", msg], cwd=r, check=True, env=e)

    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=r, check=True, env=env)
    commit("initial", "Ada", "2015-01-10", "index.js", "module.exports = 1\n")
    commit("add padding helper", "Ada", "2015-02-01", "index.js", "module.exports = pad\n")
    commit("Updated maintainers", "Bo", "2016-03-22", "package.json", '{"maintainers":["bo"]}\n')
    commit("Add MIT license", "Bo", "2016-04-01", "LICENSE", "MIT License\n")
    commit("Merge pull request #9 from someone/branch", "Bo", "2016-05-01", "README.md", "readme\n")
    return str(r)


def test_facts_come_from_git_only(grave):
    f = seance.facts(seance.load_commits(grave, diff_chars=0), today=dt.date(2026, 10, 27))
    assert (f["born"], f["born_by"], f["first_words"]) == ("2015-01-10", "Ada", "initial")
    assert f["died"] == "2016-05-01"
    assert f["last_words"] == "Add MIT license"  # a merge is not anyone's last words
    assert f["commits"] == 5 and f["souls"] == 2
    assert [who for _, who in f["keepers"]] == ["Ada", "Bo"]
    assert f["silent_days"] == (dt.date(2026, 10, 27) - dt.date(2016, 5, 1)).days


def test_tombstone_shows_the_facts(grave):
    f = seance.facts(seance.load_commits(grave, diff_chars=0), today=dt.date(2026, 10, 27))
    t = seance.tombstone("tiny-lib", f)
    assert "HERE LIES TINY-LIB" in t and '"initial"' in t and "Ada (2015) → Bo (2016)" in t


def test_recall_finds_the_right_memories(grave):
    commits = seance.load_commits(grave)
    assert seance.recall(commits, "why did you change hands?", k=1)[0]["subject"] == "Updated maintainers"
    assert seance.recall(commits, "what license are you under?", k=1)[0]["subject"] == "Add MIT license"
    assert seance.recall(commits, "favourite food?") == []


def test_citations_to_unseen_commits_are_struck():
    allowed = {"abc1234": {}, "def5678": {}}
    text, valid, struck = seance.verify("I was licensed [abc1234]. I flew to the moon [9999999].", allowed)
    assert valid == ["abc1234"] and struck == ["9999999"]
    assert "~~9999999~~" in text


def test_weakly_supported_sentence_is_flagged():
    c = {"subject": "Add MIT license", "body": "", "files": ["LICENSE"], "diff": "+MIT License", "date": "2016-04-01",
         "author": "Bo"}
    text, weak = seance.annotate("Bo added the MIT license [abc1234]. Kubernetes clusters scaled me [abc1234].",
                                 {"abc1234": c})
    assert len(weak) == 1 and "Kubernetes" in weak[0] and text.endswith("[abc1234] ⚠.")


class FakeMedium:
    def __init__(self, reply):
        self.reply = reply

    def speak(self, system, user, **kw):
        return self.reply(user) if callable(self.reply) else self.reply


def test_ask_keeps_real_citations(grave):
    def reply(prompt):
        h = next(line.split("]")[0][1:] for line in prompt.splitlines() if "Updated maintainers" in line)
        return f"Bo took over my maintainers [{h}]."
    r = seance.ask(grave, "why did you change hands?", FakeMedium(reply))
    assert r["valid"] and not r["struck"] and "Bo took over" in r["answer"]


def test_ask_with_only_invented_citations_falls_silent(grave):
    r = seance.ask(grave, "why did you change hands?", FakeMedium("I was sold for gold [1234567]."))
    assert r["valid"] == [] and r["answer"].startswith("The spirits are silent")


def test_ask_that_only_forgets_falls_silent(grave):
    def reply(prompt):
        h = prompt.split("[")[1].split("]")[0]
        return f"I do not remember [{h}]."
    r = seance.ask(grave, "why did you change hands?", FakeMedium(reply))
    assert r["valid"] == [] and r["answer"].startswith("The spirits are silent")


def test_numbers_in_verse_are_checked():
    assert seance.numbers_in("Nineteen hands, seventy-two scars, five years") == {"19", "72", "5"}
    assert seance.numbers_in("one by one they left") == set()


def test_verse_with_invented_numbers_is_retried():
    replies = iter(["Thirteen winters gone", "Nineteen hands, five years of grace"])
    m = FakeMedium(lambda _: next(replies))
    given = "72 commits by 19 people. Lived 5 years, 0 months."
    assert seance.verse(m, given, {}) == "Nineteen hands, five years of grace"


def test_citation_lists_are_split_and_each_checked():
    text = seance.split_cite_lists("Released twice [abc1234, 9999999].")
    checked, valid, struck = seance.verify(text, {"abc1234": {}})
    assert valid == ["abc1234"] and struck == ["9999999"]


def test_diff_excerpt_has_no_blob_hashes(grave):
    c = seance.load_commits(grave)
    assert all("index " not in x["diff"] and "@@" not in x["diff"] for x in c)


def test_citing_someone_elses_commit_is_flagged():
    a = {"subject": "Add WTFPL", "body": "", "files": ["package.json"], "diff": "+WTFPL", "date": "2016", "author": "Azer Koçulu"}
    b = {"subject": "License Update", "body": "", "files": ["package.json"], "diff": "+MIT", "date": "2019", "author": "100Errors"}
    _, weak = seance.annotate("Azer Koçulu added the WTFPL license [aaaaaaa], and Azer Koçulu moved it to MIT [bbbbbbb].",
                              {"aaaaaaa": a, "bbbbbbb": b})
    assert weak == ["and Azer Koçulu moved it to MIT"]
    _, ok = seance.annotate("Azer Koçulu added the WTFPL license [aaaaaaa].", {"aaaaaaa": a, "bbbbbbb": b})
    assert not ok
