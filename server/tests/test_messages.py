"""Text in two languages (messages.py): nothing the server or the Windows launcher shows escapes msg(), doc() or tr();
replies carry their message's key; a left-to-right page's document text is English. Run from server/: python -m pytest tests -q"""
import ast
import os
import re
import string
import tempfile
from pathlib import Path

os.environ.setdefault("DOCSCAN_DATA", tempfile.mkdtemp(prefix="harf-test-data-"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import messages  # noqa: E402
from engines.common import low_note  # noqa: E402
from engines.marks import LABELS, note_for  # noqa: E402
from messages import DOC_EN, Msg, doc, english, in_language, language_file, languages, msg, payload  # noqa: E402

SERVER = Path(__file__).resolve().parent.parent
FILES = [p for p in SERVER.rglob("*.py") if "tests" not in p.parts] + [SERVER.parent / "desktop" / "app.py"]
ARABIC = re.compile(r"[؀-ۿ]")
WRAPPERS = {"msg", "doc", "tr"}
# Arabic that is not text anyone reads: patterns, digit tables, the instructions to Claude, the dictionary itself
NOT_TEXT_CALLS = {"compile", "maketrans"}


def _parents(tree):
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node


def _name(call):
    f = call.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def _inside(node, kind):
    while node is not None:
        if isinstance(node, kind):
            return node
        node = getattr(node, "parent", None)
    return None


def _loose(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    _parents(tree)
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str) and ARABIC.search(node.value)):
            continue
        p = node.parent
        if isinstance(p, ast.Expr):  # a docstring
            continue
        if isinstance(p, ast.Call) and _name(p) in WRAPPERS and p.args and p.args[0] is node:
            continue
        if isinstance(p, ast.Call) and _name(p) in NOT_TEXT_CALLS:
            continue
        fn = _inside(node, ast.FunctionDef)
        if fn is not None and fn.name == "claude_prompt":
            continue
        if path.name == "messages.py" and _inside(node, ast.Dict) is not None:  # DOC_EN
            continue
        out.append(f"{path.relative_to(SERVER.parent)}:{node.lineno}: {node.value[:60]}")
    return out


def test_no_arabic_text_outside_msg_doc_or_tr():
    assert [x for f in FILES for x in _loose(f)] == []


def _holes(template):
    return {f for _, f, _, _ in string.Formatter().parse(template) if f}


def _calls():
    for path in FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _name(node) in ("msg", "doc") and node.args and isinstance(node.args[0], ast.Constant):
                yield path, node


def test_each_message_gets_exactly_its_values():
    bad = [f"{p.name}:{c.lineno}" for p, c in _calls() if _holes(c.args[0].value) != {k.arg for k in c.keywords}]
    assert bad == []


def test_every_document_text_has_its_english():
    assert [c.args[0].value for _, c in _calls() if _name(c) == "doc" and c.args[0].value not in DOC_EN] == []
    for k, v in DOC_EN.items():
        assert not ARABIC.search(v) and not re.search("[–—‘’“”]", v), k
        assert {h.split("!")[0] for h in _holes(v)} == _holes(k), k


# ---- replies
@pytest.fixture(scope="module")
def client():
    import main

    return TestClient(main.app)


def test_payload_carries_the_key_and_nested_messages():
    inner = RuntimeError(msg("تعذرت القراءة بـ EasyOCR: {error}", error="boom"))
    p = payload(msg("تعذر تنزيل القرّاء الإضافيين: {error}", error=inner))
    assert p["key"] == "تعذر تنزيل القرّاء الإضافيين: {error}"
    assert p["args"]["error"] == {"key": "تعذرت القراءة بـ EasyOCR: {error}", "args": {"error": "boom"}}
    assert p["error"] == "تعذر تنزيل القرّاء الإضافيين: تعذرت القراءة بـ EasyOCR: boom"
    assert payload(ValueError("plain")) == {"error": "plain"}


def test_a_refusal_has_its_key(client):
    r = client.get("/api/drafts/not-a-valid-id!")
    assert r.status_code in (400, 404)
    body = r.json()
    assert body["key"] in ("معرف مسودة غير صالح", "المسودة غير موجودة") and body["error"] == body["key"]


def test_an_unknown_path_still_gets_fastapis_reply(client):
    r = client.get("/api/nothing-here")
    assert r.status_code == 404 and "key" not in r.json()


def test_lang_default_and_all_languages(client, monkeypatch):
    monkeypatch.setenv("DOCSCAN_LANG", "en")
    assert client.get("/js/lang-default.js").text.strip() == 'window.HARF_LANG_DEFAULT = "en";'
    monkeypatch.setenv("DOCSCAN_LANG", "xx")  # no such language file
    assert client.get("/js/lang-default.js").text == ""
    body = client.get("/i18n/all.js").text
    for code in languages():
        assert f'I18N.add("{code}"' in body


def test_language_files_read_from_python():
    assert {"ar", "en"} <= set(languages())
    meta, words = language_file("en")
    assert meta == {"name": "English", "dir": "ltr"} and words["حفظ"] == "Save"
    assert language_file("ar")[0]["dir"] == "rtl"


def test_lang_is_for_the_windows_program(client):
    assert client.post("/api/lang", json={"lang": "en"}).status_code == 404  # a server: no


# ---- the document's own text
def test_an_english_page_gets_english_notes_and_labels():
    sign = note_for("sign", "محمد")
    blocks = [{"type": "p", "segs": [{"s": "Dear "}, {"s": doc("[{label}]", label=LABELS["sign"]), "note": sign}]},
              {"type": "table", "rows": [[[{"s": "x", "note": low_note(40)}]]]}]
    in_language(blocks, "en")
    seg = blocks[0]["segs"][1]
    assert seg["s"] == "[Signature]"
    assert seg["note"].startswith("The machine reading can't read this signature in the photo") and '"محمد"' in seg["note"]
    assert blocks[1]["rows"][0][0][0]["note"] == "Uncertain reading (confidence 40%). Compare it with the original photo."


def test_an_arabic_page_keeps_its_arabic():
    blocks = [{"type": "p", "segs": [{"s": "x", "note": low_note(40)}]}]
    in_language(blocks, "ar")
    assert blocks[0]["segs"][0]["note"] == "قراءة غير مؤكدة (درجة الثقة 40%)، قارن مع الصورة الأصلية"
    assert isinstance(blocks[0]["segs"][0]["note"], Msg)


def test_english_reads_nested_values():
    assert english(doc("[{label}]", label=doc("ختم"))) == "[Stamp]"
    assert messages.english("plain") == "plain"
