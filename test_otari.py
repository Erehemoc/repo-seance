"""Otari mode without the network: a fake gateway stands in for api.otari.ai."""
import seance
import otari_medium as om

RESULTS = [
    {"title": "How one developer just broke Node, Babel and thousands of projects in 11 lines of JavaScript",
     "url": "https://example.org/left-pad-npm",
     "snippet": "Azer Koçulu unpublished left-pad and his other npm modules after a dispute with Kik over a "
                "package name. Builds across the JavaScript world broke."},
    {"title": "Kik's statement", "url": "https://example.org/kik",
     "snippet": "Kik asked npm to transfer the kik package name."},
]


class FakeGateway:
    def __init__(self, reply, results=RESULTS, fallback=False):
        self.reply, self.results, self.fallback, self.calls = reply, results, fallback, []

    def __call__(self, path, body, key, base_url, timeout=120):
        self.calls.append((path, body))
        if path == "/search":
            return {"object": "search", "results": self.results}, {}
        text = self.reply(body) if callable(self.reply) else self.reply
        headers = {"otari-provider": "deepinfra", "otari-model": "gemma-3-27b-it",
                   "otari-fallback": "true" if self.fallback else "false",
                   "otari-attempt-count": "2" if self.fallback else "1"}
        return {"model": body["model"], "choices": [{"message": {"content": text}}]}, headers


def medium(reply, **kw):
    return om.OtariMedium("seance", key="otk_test", post=FakeGateway(reply, **kw))


def test_speak_sends_an_openai_style_request_and_records_the_voice():
    m = medium("Five years breathed.")
    assert m.speak("sys", "user") == "Five years breathed."
    path, body = m._post.calls[0]
    assert path == "/chat/completions" and body["model"] == "seance"
    assert [x["role"] for x in body["messages"]] == ["system", "user"]
    assert m.who() == "the medium: gemma-3-27b-it via deepinfra on Otari"


def test_a_fallback_is_reported():
    m = medium("ok", fallback=True)
    m.speak("s", "u")
    assert "fallback after 1 failed attempt" in m.who()


def test_rumours_keep_real_sources_and_strike_invented_ones():
    reply = ("Azer Koçulu unpublished me from npm after a dispute with Kik over a package name [r1]. "
             "I was rewritten in Rust by aliens [r7].")
    r = om.rumours("left-pad", "why were you removed from npm?", medium(reply), seance.support)
    assert r["cited"] == ["r1"] and r["struck"] == ["r7"]
    assert "~~r7~~" in r["text"] and r["sources"][0][1]["url"] == "https://example.org/left-pad-npm"


def test_rumour_that_says_more_than_its_source_is_flagged():
    reply = "Kik asked npm for the kik package name [r2]. Kubernetes clusters crashed for a decade [r2]."
    r = om.rumours("left-pad", "why?", medium(reply), seance.support)
    assert len(r["weak"]) == 1 and "Kubernetes" in r["weak"][0]


def test_no_results_means_the_living_are_silent():
    r = om.rumours("left-pad", "favourite food?", medium("anything", results=[]), seance.support)
    assert r["text"] == "The living say nothing of that." and not r["sources"]


def test_ask_through_otari_still_strikes_unseen_commits(tmp_path):
    import subprocess, os
    r = tmp_path / "tiny"
    r.mkdir()
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_AUTHOR_NAME="Ada", GIT_AUTHOR_EMAIL="a@x",
               GIT_COMMITTER_NAME="Ada", GIT_COMMITTER_EMAIL="a@x")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=r, check=True, env=env)
    (r / "LICENSE").write_text("MIT License\n")
    subprocess.run(["git", "add", "."], cwd=r, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "Add MIT license"], cwd=r, check=True, env=env)

    def reply(body):
        h = body["messages"][1]["content"].split("[")[1].split("]")[0]
        return f"Ada gave me the MIT license [{h}]. I was sold for gold [1234567]."
    out = seance.ask(str(r), "what license?", medium(reply))
    assert out["valid"] and out["struck"] == ["1234567"]


def test_key_comes_from_env_or_file_and_is_never_echoed(tmp_path, monkeypatch):
    monkeypatch.delenv("OTARI_API_KEY", raising=False)
    f = tmp_path / "k.txt"
    f.write_text("otk_secret\n")
    assert om.api_key(str(f)) == "otk_secret"
    monkeypatch.setenv("OTARI_API_KEY", "otk_env")
    assert om.api_key(str(f)) == "otk_env"
