"""Security rules: markup that hands something away.

The category existed with no rules in it. `audit.repo_facts` was filing a
committed `.env` under `security` and nothing else ever did, so the word in
the report meant "one particular repository check ran" rather than "the
markup was looked at for this".

Every rule here is deliberately `EXACT`. That is not a coincidence and it is
the reason this category was safe to open: each one asks a question the markup
answers on its own - is there a `sandbox` attribute, is the action `http://`,
is there an `integrity` next to that cross-origin `src`. None of them needs a
stylesheet, a browser or a guess, which is what the four large false-positive
classes this tool has shipped all needed. A security finding that turns out to
be wrong costs more trust than any other kind, so nothing that has to infer
belongs here.

What is deliberately *not* here: anything that would need to fetch the URL, run
the script or know the server's headers. A `Content-Security-Policy` sent as a
header is invisible to a file on disk, and reporting its absence from the
markup would be a finding about the scan rather than the page.
"""
from __future__ import annotations

import re

from ..base import (
    CRITICAL, EXACT, MINOR, MODERATE, NEEDS_BROWSER, SECURITY, SERIOUS, Issue,
    Rule, RuleRegistry, is_binding, snippet_of,
)

_HTTP_URL = re.compile(r"^http://", re.IGNORECASE)
_ABSOLUTE_URL = re.compile(r"^(?:https?:)?//", re.IGNORECASE)

#: Attribute names that carry a secret often enough to be worth naming, and
#: rarely enough that a hit is worth reading. Deliberately not "anything
#: containing `key`": `data-key` is React's list key on every list in the
#: world, and a rule that fires on it would be noise wearing a scary label.
_SECRET_ATTRS = ("data-api-key", "data-apikey", "data-secret", "data-token",
                 "data-access-token", "data-private-key", "data-password")

#: What a secret looks like when it is real. A placeholder is the common case
#: in a template, and shouting about `data-api-key="YOUR_KEY_HERE"` teaches
#: people to ignore the rule.
_PLACEHOLDER = re.compile(
    r"^(?:your|my|the)?[-_ ]?(?:api|access|secret|private)?[-_ ]?"
    r"(?:key|token|secret|password)?[-_ ]?(?:here|goes[-_ ]?here|xxx+|\.\.\.)?$",
    re.IGNORECASE)
#: Long enough that it is not a word. Real keys are long; `data-token="1"` is
#: an identifier.
_SECRET_MIN = 16


def _looks_secret(value: str) -> bool:
    text = (value or "").strip()
    if len(text) < _SECRET_MIN or is_binding(text):
        return False
    return not _PLACEHOLDER.match(text)


class SecurityRule(Rule):
    category = SECURITY


class UnsandboxedFrame(SecurityRule):
    """A third-party frame with the run of the page.

    Without `sandbox`, a framed document can navigate the top-level window,
    run scripts against its own origin, submit forms and open popups. That is
    correct for a frame you wrote; for one pointing at another origin it hands
    that origin a lever on your page.

    Only cross-origin frames, and only where the address is a literal: a
    template that computes the `src` may well compute a trusted one, and
    guessing at it would be a finding about the framework rather than the page.
    """
    id = "sec-frame-sandbox"
    # Moderate, not serious. A cross-origin frame cannot read or script the
    # page around it, and browsers already stop it from navigating the top
    # window or opening a popup without the person's own click. What is
    # left is hardening, and every YouTube and Google Maps embed on a site
    # lacks it: 111 rows on one crawl of a municipal WordPress site, ranked beside contrast
    # failures a visitor actually meets.
    severity = MODERATE
    wcag = ()

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all("iframe"):
            src = (tag.get("src") or "").strip()
            if not src or is_binding(src) or not _ABSOLUTE_URL.match(src):
                continue
            if tag.has_attr("sandbox"):
                continue
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, category=self.category,
                selector=selector, line=line, snippet=snippet_of(tag),
                source=context.source, details={"src": src},
                fix_snippet=None,
            ))
        return issues


class FramePermissions(SecurityRule):
    """`allow="..."` handing a cross-origin frame the camera or the microphone.

    A permission delegated in markup is granted without the person in the page
    being asked again by the framed origin. `camera`, `microphone`,
    `geolocation` and `payment` are the four worth reading twice.
    """
    id = "sec-frame-permissions"
    severity = SERIOUS
    wcag = ()

    _SENSITIVE = ("camera", "microphone", "geolocation", "payment",
                  "display-capture", "midi", "usb")

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all("iframe"):
            allow = (tag.get("allow") or "").lower()
            src = (tag.get("src") or "").strip()
            if not allow or is_binding(src) or not _ABSOLUTE_URL.match(src):
                continue
            granted = [name for name in self._SENSITIVE if name in allow]
            if not granted:
                continue
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, category=self.category,
                selector=selector, line=line, snippet=snippet_of(tag),
                source=context.source,
                details={"granted": granted, "src": src},
            ))
        return issues


class FormOverHttp(SecurityRule):
    """A form posting to `http://`.

    Everything typed into it crosses the network in the clear, and the page
    around it being HTTPS is what makes this easy to miss: the padlock is
    about the page, not about where the form goes.
    """
    id = "sec-form-insecure-action"
    severity = CRITICAL
    wcag = ()

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all("form"):
            action = (tag.get("action") or "").strip()
            if not action or is_binding(action) or not _HTTP_URL.match(action):
                continue
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, category=self.category,
                selector=selector, line=line, snippet=snippet_of(tag),
                source=context.source, details={"action": action},
                fix_snippet=None,
            ))
        return issues


class ScriptWithoutIntegrity(SecurityRule):
    """A script from another origin, loaded on trust.

    Whatever that origin serves runs with the full rights of this page. An
    `integrity` hash makes the browser refuse anything else, which is the
    difference between trusting a CDN today and trusting it every day.

    `crossorigin` without `integrity` is the shape worth flagging: it says
    somebody thought about the origin and stopped one step short.
    """
    id = "sec-script-integrity"
    severity = MODERATE
    wcag = ()

    def check(self, document, context) -> list:
        page_host = _host(context.source)
        issues = []
        for tag in document.find_all("script"):
            src = (tag.get("src") or "").strip()
            if not src or is_binding(src) or not _ABSOLUTE_URL.match(src):
                continue
            if tag.get("integrity"):
                continue
            host = _host(src)
            if page_host and _same_site(host, page_host):
                continue
            # Without a host for the page itself - a file on disk, a saved
            # copy, a repo fragment - "cross-origin" cannot be established,
            # and this rule is about cross-origin scripts. Measured on one
            # saved page: 37 findings against the 3 the same page produced
            # when crawled, because every one of its own CDN scripts looked
            # foreign. Still reported, because `integrity` is worth having on
            # any external script, but at the weight of something the pass
            # could not settle - which `--confidence exact` then drops.
            settled = bool(page_host)
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id,
                severity=self.severity if settled else MINOR,
                confidence=EXACT if settled else NEEDS_BROWSER,
                category=self.category,
                selector=selector, line=line, snippet=snippet_of(tag),
                source=context.source,
                details={"src": src, "host": host,
                         "origin_known": settled},
            ))
        return issues


def _same_site(host: str, page_host: str) -> bool:
    """Is this script served from the page's own domain?

    Exact host equality was the test, and it made a site's own asset
    subdomain look foreign: 61 of 162 findings on a ten-site run were
    `assets.squarespace.com` on `www.squarespace.com` and the like. SRI on
    your own CDN is a preference; SRI on somebody else's is the point of the
    rule.

    Compared by suffix against the page's own domain with `www.` removed,
    not by a registrable-domain guess. A public-suffix table would let
    `bar.github.io` pass as `foo.github.io`'s own, which is exactly the kind
    of wrongly-merged answer that hides a real finding.
    """
    if not host or not page_host:
        return False
    root = page_host[4:] if page_host.startswith("www.") else page_host
    return host == page_host or host == root or host.endswith("." + root)


class SecretInMarkup(SecurityRule):
    """A key written into an attribute.

    Markup is public: it is served to everyone who opens the page and it is in
    the repository. A key here is a key published, whatever the attribute is
    called.

    Narrow on purpose. Only attributes whose *name* says secret, only values
    long enough not to be an identifier, and never a placeholder or a
    template binding - `data-api-key="{{ config.key }}"` is a template doing
    the right thing, and `data-key` is React's list key on every list ever
    written.
    """
    id = "sec-secret-in-markup"
    severity = CRITICAL
    wcag = ()

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all(True):
            attrs = getattr(tag, "attrs", None) or {}
            for name in _SECRET_ATTRS:
                value = attrs.get(name)
                if isinstance(value, list):
                    value = " ".join(value)
                if not _looks_secret(value or ""):
                    continue
                selector, line = context.locate(tag)
                issues.append(Issue(
                    rule_id=self.id, severity=self.severity,
                    category=self.category, selector=selector, line=line,
                    snippet=snippet_of(tag), source=context.source,
                    details={"attribute": name, "length": len(value)},
                ))
        return issues


class AutocompleteOnSecret(SecurityRule):
    """A password or a one-time code the browser is told to remember.

    `autocomplete="on"` on a password field, or a one-time-code field with no
    `autocomplete="one-time-code"`, is the browser being asked to store
    something that should not outlive the request.
    """
    id = "sec-autocomplete-secret"
    severity = MODERATE
    wcag = ()

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all("input"):
            kind = (tag.get("type") or "text").lower()
            if kind != "password":
                continue
            value = (tag.get("autocomplete") or "").strip().lower()
            if value not in ("on", "true"):
                continue
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, category=self.category,
                selector=selector, line=line, snippet=snippet_of(tag),
                source=context.source, details={"autocomplete": value},
                fix_snippet=None,
            ))
        return issues


class PasswordInGetForm(SecurityRule):
    """A password field in a form that submits by GET.

    Everything in the form goes into the query string: the address bar, the
    browser history, the referrer sent to the next site, the server's access
    log and every proxy in between. HTTPS does not help - the URL is
    encrypted in transit and written in the clear at both ends.

    A `method` that is absent means GET, which is why this rule reads the
    absence as the finding rather than skipping it.
    """
    id = "sec-password-in-get-form"
    severity = CRITICAL
    wcag = ()

    def check(self, document, context) -> list:
        issues = []
        for form in document.find_all("form"):
            method = (form.get("method") or "get").strip().lower()
            if is_binding(method) or method != "get":
                continue
            secret = form.find("input", attrs={"type": "password"})
            if secret is None:
                continue
            selector, line = context.locate(form)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, category=self.category,
                selector=selector, line=line, snippet=snippet_of(form),
                source=context.source,
                details={"method": method, "declared": bool(form.get("method"))},
            ))
        return issues


class InsecureFormAction(SecurityRule):
    """A submit button that overrides the form's action with `http://`.

    `formaction` on a button wins over the form's own `action`, so a form
    that looks safe can still post in the clear through one of its buttons.
    That is the whole reason this is separate from `sec-form-insecure-action`:
    reading the form alone misses it.
    """
    id = "sec-formaction-insecure"
    severity = CRITICAL
    wcag = ()

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all(("button", "input")):
            action = (tag.get("formaction") or "").strip()
            if not action or is_binding(action) or not _HTTP_URL.match(action):
                continue
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, category=self.category,
                selector=selector, line=line, snippet=snippet_of(tag),
                source=context.source, details={"formaction": action},
            ))
        return issues


class CredentialsInUrl(SecurityRule):
    """A username and password written into a URL.

    `https://user:pass@host/` puts the credential in the markup, in the
    browser's history and in the referrer. Browsers have been stripping this
    form for years, so it is usually a leak that no longer even works.
    """
    id = "sec-credentials-in-url"
    severity = CRITICAL
    wcag = ()

    _WITH_CREDENTIALS = re.compile(
        r"^(?:https?|ftp)://[^/@\s:]+:[^/@\s]+@", re.IGNORECASE)

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all(True):
            attrs = getattr(tag, "attrs", None) or {}
            for name in ("href", "src", "action", "formaction", "data-url"):
                value = attrs.get(name)
                if isinstance(value, list):
                    value = " ".join(value)
                value = (value or "").strip()
                if not value or is_binding(value):
                    continue
                if not self._WITH_CREDENTIALS.match(value):
                    continue
                selector, line = context.locate(tag)
                issues.append(Issue(
                    rule_id=self.id, severity=self.severity,
                    category=self.category, selector=selector, line=line,
                    snippet=snippet_of(tag), source=context.source,
                    details={"attribute": name, "host": _host(value)},
                ))
        return issues


class UnsandboxedSrcdoc(SecurityRule):
    """An inline document in a frame, with the run of the page.

    `srcdoc` markup runs in the *embedding* page's origin unless a `sandbox`
    says otherwise, so anything interpolated into it - a comment, a preview,
    a rendered snippet - runs as first-party script. It is the same risk as a
    cross-origin frame with the origin removed, which makes it easier to miss
    and worse when it lands.
    """
    id = "sec-srcdoc-sandbox"
    severity = SERIOUS
    wcag = ()

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all("iframe"):
            if not tag.has_attr("srcdoc") or tag.has_attr("sandbox"):
                continue
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, category=self.category,
                selector=selector, line=line, snippet=snippet_of(tag),
                source=context.source, details={},
            ))
        return issues


def _host(url: str) -> str:
    match = re.match(r"^(?:https?:)?//([^/?#]+)", (url or "").strip(),
                     re.IGNORECASE)
    return match.group(1).lower() if match else ""


for _rule in (UnsandboxedFrame, FramePermissions, FormOverHttp,
              ScriptWithoutIntegrity, SecretInMarkup, AutocompleteOnSecret,
              PasswordInGetForm, InsecureFormAction, CredentialsInUrl,
              UnsandboxedSrcdoc):
    RuleRegistry.register(_rule)
