"""Text by name (messages.py, web/i18n/*.json): no Arabic text left in the server or the Windows launcher, every
msg(), doc() and tr() name exists with exactly its values, replies carry their name, and a left-to-right page's
document text is English. Run from server/: python -m pytest tests -q"""
import ast
import os
import re
import string
import tempfile
from pathlib import Path

os.environ.setdefault("DOCSCAN_DATA", tempfile.mkdtemp(prefix="harf-test-data-"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from engines.common import low_note  # noqa: E402
from engines.marks import LABELS, note_for  # noqa: E402
from messages import Msg, doc, in_language, language_file, languages, msg, payload, render  # noqa: E402

SERVER = Path(__file__).resolve().parent.parent
FILES = [p for p in SERVER.rglob("*.py") if "tests" not in p.parts] + [SERVER.parent / "desktop" / "app.py"]
ARABIC = re.compile("[؀-ۿ]")
SOURCE = language_file("ar")[1]
# Arabic that is about the document's own text, not words anyone is shown: patterns and digit tables
PATTERN_CALLS = {"compile", "maketrans"}


def _name(call):
    f = call.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def _trees():
    for path in FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                child.parent = node
        yield path, tree


def _under(node, test):
    while node is not None:
        if test(node):
            return True
        node = getattr(node, "parent", None)
    return False


def test_no_arabic_text_in_the_code():
    loose = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str) and ARABIC.search(node.value)):
                continue
            if isinstance(node.parent, ast.Expr):  # a docstring
                continue
            if _under(node, lambda n: isinstance(n, ast.Call) and _name(n) in PATTERN_CALLS):
                continue
            # Claude's instructions quote the kind of text it will find ("أولاً:"); its own words come from the files
            if _under(node, lambda n: isinstance(n, ast.FunctionDef) and n.name == "claude_prompt"):
                continue
            loose.append(f"{path.relative_to(SERVER.parent)}:{node.lineno}: {node.value[:60]}")
    assert loose == []


def _holes(template):
    return {f for _, f, _, _ in string.Formatter().parse(template) if f}


def _other(v):
    return v["other"] if isinstance(v, dict) else v


def test_each_name_exists_with_exactly_its_values():
    bad = []
    for path, tree in _trees():
        for c in ast.walk(tree):
            if isinstance(c, ast.Call) and _name(c) in ("msg", "doc", "tr") and c.args and isinstance(c.args[0], ast.Constant):
                key = c.args[0].value
                if key not in SOURCE:
                    bad.append(f"{path.name}:{c.lineno}: no {key}")
                elif _name(c) != "tr" and _holes(_other(SOURCE[key])) != {k.arg for k in c.keywords}:
                    bad.append(f"{path.name}:{c.lineno}: values of {key}")
                elif _name(c) == "doc" and not key.startswith("doc."):
                    bad.append(f"{path.name}:{c.lineno}: doc() takes doc.* names")
    assert bad == []


# ---- replies
@pytest.fixture(scope="module")
def client():
    import main

    return TestClient(main.app)


def test_payload_carries_the_name_and_nested_messages():
    inner = RuntimeError(msg("server.couldntReadEasyocr", error="boom"))
    p = payload(msg("server.couldntDownloadExtraReaders", error=inner))
    assert p["key"] == "server.couldntDownloadExtraReaders"
    assert p["args"]["error"] == {"key": "server.couldntReadEasyocr", "args": {"error": "boom"}}
    assert p["error"] == render("ar", "server.couldntDownloadExtraReaders", error=render("ar", "server.couldntReadEasyocr", error="boom"))
    assert payload(ValueError("plain")) == {"error": "plain"}


def test_a_refusal_has_its_name(client):
    r = client.get("/api/drafts/not-a-valid-id!")
    assert r.status_code in (400, 404)
    body = r.json()
    assert body["key"] in ("server.invalidDraftId", "server.draftNotFound") and body["error"] == SOURCE[body["key"]]


def test_an_unknown_path_still_gets_fastapis_reply(client):
    r = client.get("/api/nothing-here")
    assert r.status_code == 404 and "key" not in r.json()


def test_labels_go_out_as_names(client):
    eng = {e["id"]: e["label"] for e in client.get("/api/engines").json()["engines"]}
    assert eng["paddle"] == {"key": "reader.paddleocrRecommended", "args": {}} and eng["easyocr"] == "EasyOCR"
    tpl = client.get("/api/templates").json()["templates"]
    assert {"key": "template.noHeader", "args": {}} in [t["name"] for t in tpl]


def test_lang_default_and_all_languages(client, monkeypatch):
    monkeypatch.setenv("DOCSCAN_LANG", "en")
    assert client.get("/js/lang-default.js").text.strip() == 'window.HARF_LANG_DEFAULT = "en";'
    monkeypatch.setenv("DOCSCAN_LANG", "xx")  # no such language file
    assert client.get("/js/lang-default.js").text == ""
    body = client.get("/i18n/all.js").text
    for code in languages():
        assert f'I18N.add("{code}", {{"_meta"' in body


def test_language_files():
    assert {"ar", "en"} <= set(languages())
    meta, words = language_file("en")
    assert meta == {"name": "English", "dir": "ltr"} and words["ui.save"] == "Save"
    assert language_file("ar")[0]["dir"] == "rtl"


def test_lang_is_for_the_windows_program(client):
    assert client.post("/api/lang", json={"lang": "en"}).status_code == 404  # a server: no


# ---- the document's own text
def test_an_english_page_gets_english_notes_and_labels():
    blocks = [{"type": "p", "segs": [{"s": "Dear "}, {"s": doc("doc.bracketLabel", label=LABELS["sign"]), "note": note_for("sign", "محمد")}]},
              {"type": "table", "rows": [[[{"s": "x", "note": low_note(40)}]]]}]
    in_language(blocks, "en")
    seg = blocks[0]["segs"][1]
    assert seg["s"] == "[Signature]"
    assert seg["note"].startswith("The machine reading can't read this signature in the photo") and '"محمد"' in seg["note"]
    assert blocks[1]["rows"][0][0][0]["note"] == "Uncertain reading (confidence 40%). Compare it with the original photo."


def test_an_arabic_page_keeps_its_arabic():
    blocks = [{"type": "p", "segs": [{"s": "x", "note": low_note(40)}]}]
    in_language(blocks, "ar")
    assert blocks[0]["segs"][0]["note"] == SOURCE["doc.uncertainReadingConfidenceCompareOriginal"].format(conf=40)
    assert isinstance(blocks[0]["segs"][0]["note"], Msg)


def test_render_plurals_and_fallback():
    assert render("ar", "app.pageCount", n=2) == "صفحتان"
    assert render("en", "app.pageCount", n=0) == "No pages"
    assert render("xx", "ui.save") == SOURCE["ui.save"]  # no such language: the Arabic
