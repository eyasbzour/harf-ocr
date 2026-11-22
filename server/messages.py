"""Text in two languages. The Arabic text is the key, as in the browser (web/js/i18n.js).

msg(): a message for the screen. It is the Arabic text, and also carries its key and values, so a reply can send
{"error", "key", "args"} (payload) and the browser shows it in the chosen language (web/i18n/en.js has the English).

doc(): text the readers write into the document: a note on an uncertain word, "[توقيع]" in place of a signature.
It follows the page's language, not the interface: in_language() puts a left-to-right page's in English (DOC_EN).
"""
from __future__ import annotations

import json
import re
import string
from pathlib import Path

# ---- the interface languages: one file each, web/i18n/<code>.js, I18N.add("<code>", {name, dir}, {key: text})
# (web/js/i18n.js). The server serves them as one script and takes the codes from here; the Windows program's
# launcher reads its few words from them. Arabic is the source: the text in the code, and the fallback.
LANG_DIR = Path(__file__).resolve().parent.parent / "web" / "i18n"
SOURCE = "ar"


def languages() -> list[str]:
    return sorted(p.stem for p in LANG_DIR.glob("*.js"))


def language_file(code: str) -> tuple[dict, dict]:
    """A language file's {name, dir} and its entries (the file is strict JSON inside I18N.add(...))."""
    text = "\n".join(ln for ln in (LANG_DIR / f"{code}.js").read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("//"))
    m = re.fullmatch(r'\s*I18N\.add\("(\w+)",\s*(\{.*?\}),\s*(\{.*\})\);\s*', text, re.S)
    if not m or m.group(1) != code:
        raise ValueError(f"web/i18n/{code}.js is not I18N.add(\"{code}\", {{name, dir}}, {{...}});")
    return json.loads(m.group(2)), json.loads(m.group(3))


class Msg(str):
    """The Arabic text, with the template and values it was made from."""
    key: str
    args: dict

    def __new__(cls, key: str, **args):
        self = super().__new__(cls, key.format(**{k: str(v) for k, v in args.items()}) if args else key)
        self.key, self.args = key, args
        return self


def msg(key: str, **args) -> Msg:
    return Msg(key, **args)


def doc(key: str, **args) -> Msg:
    assert key in DOC_EN, key  # tests/test_i18n.py: every doc() text has its English
    return Msg(key, **args)


def _of(v):
    """The message an exception carries, when it carries one."""
    if isinstance(v, BaseException) and v.args and isinstance(v.args[0], Msg):
        return v.args[0]
    return v


def _arg(v):
    v = _of(v)
    if isinstance(v, Msg):
        return {"key": v.key, "args": {k: _arg(x) for k, x in v.args.items()}}
    return str(v)


def payload(m) -> dict:
    """{"error": the Arabic text, "key", "args"} for a reply; an exception's message when it has one."""
    m = _of(m)
    if isinstance(m, Msg):
        return {"error": str(m), "key": m.key, "args": {k: _arg(x) for k, x in m.args.items()}}
    return {"error": str(m)}


# ---- text written into the document
DOC_EN = {
    "قراءة غير مؤكدة (درجة الثقة {conf}%)، قارن مع الصورة الأصلية":
        "Uncertain reading (confidence {conf}%). Compare it with the original photo.",
    "تأشيرة بخط اليد": "Handwritten note",
    "توقيع": "Signature",
    "ختم": "Stamp",
    "[{label}]": "[{label}]",
    " القراءة الآلية التقريبية: «{text}».": " The rough machine reading: \"{text}\".",
    "{label} في الصورة لا تقرؤه القراءة الآلية بدقة.{guess} اكتب نصه هنا أو احذف هذا الموضع.":
        "The machine reading can't read this {label!l} in the photo accurately.{guess} Type its text here or delete this spot.",
    # the number check runs on Arabic pages only (engines/__init__.py), but its note is document text all the same
    "رقم قرأه Tesseract ولم يظهر في قراءة PaddleOCR، تحقق منه في الصورة":
        "A number Tesseract read that PaddleOCR missed. Check it in the photo.",
    # Claude's (ai_engines.py): its own notes are written in Arabic, as its instructions ask
    "غير مؤكد": "Uncertain",
    "(موضع الملاحظة تقريبي) ": "(the note's place is approximate) ",
    "ملاحظة": "Note",
}


class _Format(string.Formatter):
    """{x!l}: the value in lower case ("this signature")."""

    def convert_field(self, value, conversion):
        return str(value).lower() if conversion == "l" else super().convert_field(value, conversion)


def english(v) -> str:
    """A doc() text in English; its values too."""
    if not isinstance(v, Msg):
        return str(v)
    return _Format().format(DOC_EN[v.key], **{k: english(x) for k, x in v.args.items()})


def in_language(blocks: list[dict], lang: str) -> list[dict]:
    """The doc() text in the blocks (segments' text and notes, in paragraphs and table cells) in lang."""
    if lang != "en":
        return blocks

    def segs(ss):
        for sg in ss or []:
            for k in ("s", "note"):
                if isinstance(sg.get(k), Msg):
                    sg[k] = english(sg[k])

    for b in blocks:
        segs(b.get("segs"))
        for row in b.get("rows") or []:
            for cell in row:
                segs(cell)
    return blocks
