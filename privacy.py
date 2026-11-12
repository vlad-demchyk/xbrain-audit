"""Personal data and secrets out of everything a run writes. One owner.

An audit quotes the page: an element's opening tag, its address, the text a
rule complained about. On a site behind a sign-in that page is rendered *for
the person signed in*, and it carries them in its markup - a survey embedded
as `<iframe src="https://survey.example/home?username=<login>&hash=<per-user
access hash>">`, a `mailto:` with a colleague's address, a token on a link.
Quoted as-is, the report hands the auditor's identity and a working access
link to everyone the report is sent to.

So the values are masked where the finding is born (`audit.base.Issue`), and
again at each boundary where text leaves the process: the JSON payload, the
Markdown and HTML (and so PDF) reports, the progress lines on stderr and the
browser's console lines Qt forwards there. Masked at birth means every
consumer downstream - the deduplicator, the zone classifier, the report
writers, the window - sees one spelling, and two places can never disagree
about what was hidden.

What is masked:

* the **value** of a query parameter whose name says it is personal or a
  credential (`SENSITIVE_PARAMETERS`), in a plain URL, in HTML where `&` is
  written `&amp;`, and percent-encoded inside another URL's parameter. The
  name stays: "this link carried a username" is the finding, the username
  is not;
* **e-mail addresses**, anywhere, including `%40`-encoded ones. A file name
  like `logo@2x.png` is not an address and is left alone.

**Fingerprints** (`suppression.fingerprint`) are computed from the masked
text. Decided, not incidental: a per-user hash changes with the person and
the session, so a fingerprint over the raw value would be a different finding
on every run and every `.xaudit-ignore` entry for it would expire at once.
Masked, the same finding has the same fingerprint for everybody, and the
fingerprint in the JSON is the one a reader recomputes from the JSON. An
ignore entry written before masking existed, for one of these findings, no
longer matches; it has to be written again.

What is **not** masked, and why: the path of an address (it is where the
problem is), parameter names, and attribute values with no personal shape.
This is a filter over known shapes, not a guarantee that nothing personal is
left; a report about a signed-in site should still be shared with care.
"""
from __future__ import annotations

import re

#: Query parameters whose value is personal or a credential. Compared
#: case-insensitively and by the whole name.
SENSITIVE_PARAMETERS = (
    "username", "user", "email", "mail", "hash", "token", "access_token",
    "auth", "key", "sig", "signature", "session", "sid", "code", "password",
    "pwd", "upn", "login",
)

#: What a masked value becomes.
PLACEHOLDER = "[masked]"
#: What an e-mail address becomes.
EMAIL_PLACEHOLDER = "[email]"

_NAMES = "|".join(sorted((re.escape(name) for name in SENSITIVE_PARAMETERS),
                         key=len, reverse=True))

#: `?name=value`, `&name=value`, `&amp;name=value`, `#name=value`. The value
#: ends where the next parameter, the fragment, a quote, a tag or whitespace
#: begins.
_PARAMETER = re.compile(
    rf"(?<=[?&;#])({_NAMES})=([^&#\s\"'<>]*)", re.I)
#: The same, percent-encoded inside another parameter (`%3F`, `%26`, `%3D`).
_ENCODED_PARAMETER = re.compile(
    rf"(?<=%3[fF]|%26)({_NAMES})%3[dD]((?:(?!%26)[^&#\s\"'<>])*)", re.I)

#: Extensions that make `name@2x.png` a file rather than an address.
_FILE_SUFFIXES = frozenset((
    "png", "jpg", "jpeg", "gif", "svg", "webp", "avif", "ico", "bmp", "tif",
    "tiff", "css", "js", "mjs", "json", "map", "pdf", "woff", "woff2", "ttf",
    "otf", "eot", "html", "htm", "xml", "mp4", "webm", "mp3", "ogg", "wav",
    "txt", "zip",
))
_EMAIL = re.compile(
    r"(?<![\w.%+-])[A-Za-z0-9._%+-]+(?:@|%40)((?:[A-Za-z0-9-]+\.)+([A-Za-z]{2,24}))(?![\w-])")


def _email(match) -> str:
    if match.group(2).lower() in _FILE_SUFFIXES:
        return match.group(0)
    return EMAIL_PLACEHOLDER


def mask_text(text):
    """`text` with sensitive parameter values and e-mail addresses masked.

    Anything that is not a string comes back unchanged, so callers can pass
    a field without checking it first. Idempotent.
    """
    if not isinstance(text, str) or not text:
        return text
    if "=" in text or "%3" in text.lower():
        text = _PARAMETER.sub(lambda m: f"{m.group(1)}={PLACEHOLDER}"
                              if m.group(2) else m.group(0), text)
        text = _ENCODED_PARAMETER.sub(
            lambda m: f"{m.group(1)}%3D{PLACEHOLDER}" if m.group(2) else m.group(0),
            text)
    if "@" in text or "%40" in text:
        text = _EMAIL.sub(_email, text)
    return text


def mask_value(value):
    """`mask_text` over every string in a JSON-shaped value, keys included."""
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, dict):
        return {mask_text(key) if isinstance(key, str) else key: mask_value(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [mask_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(mask_value(item) for item in value)
    return value


def mask_issue(issue) -> None:
    """Mask a finding's quoted text in place: snippet, fix, selector, details.

    Not `source`: it is the key every document, cache and page map is joined
    on, and it is masked where it is written out (`mask_value` over the
    payload) instead.
    """
    for name in ("snippet", "fix_snippet", "selector"):
        value = getattr(issue, name, None)
        if isinstance(value, str) and value:
            setattr(issue, name, mask_text(value))
    details = getattr(issue, "details", None)
    if isinstance(details, dict) and details:
        issue.details = mask_value(details)
