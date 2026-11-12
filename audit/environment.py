"""Findings that describe the machine a page was served from, not the page.

A crawl of `http://town.local` reported 365 critical findings. Every one
was a form whose `action` was `http://...`, because a local development site
is served over plain HTTP: there is nothing to change in the code. Beside them,
381 pages each missing a `Content-Security-Policy`, `X-Content-Type-Options`,
`Referrer-Policy` and `X-Frame-Options` header, which a local nginx does not
send and a production server does. The developer read the top of the list,
spent time on it, and found that none of it was a defect in the project.

So on a local target these findings are **left out of the list and counted**.
Not deleted silently: the run says how many it left out and why, `--json`
carries them as `environment`, and `--include-environment` puts them back. The
same shape as `--unsettled`, for the same reason: hiding a number is how a
report starts to lie by omission, and showing everything is how it stops being
read.

What is *not* in the list: anything about the markup, the scripts, the images,
the accessibility or the SEO of the page. A third-party script loaded
synchronously is as much a defect on `town.local` as on `town.example.it`.
Only what the server (not the code) decides, and what a plain-HTTP address
makes inevitable, is environment.

Applied to a **web** audit only. In repo mode a template containing
`action="http://..."` is a finding about the code, and stays one.
"""
from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

#: What the server decides or a plain-HTTP address makes inevitable. Every id
#: here is something a production deployment fixes without touching the
#: project's source: response headers, compression, caching, and the
#: crawl-control signals a development copy sets on purpose.
LOCAL_ONLY_RULES = frozenset({
    # Response headers the web server adds.
    "sec-no-csp", "sec-no-hsts", "sec-no-nosniff",
    "sec-no-referrer-policy", "sec-no-frame-options",
    # How the server delivers bytes.
    "perf-no-compression", "perf-no-cache-header",
    # A local site is not on HTTPS, so a form posting back to itself is `http`.
    "sec-form-insecure-action", "sec-formaction-insecure",
    # A development copy is told to stay out of search engines on purpose, and
    # a local robots.txt and sitemap are not the production ones.
    "seo-noindex", "seo-x-robots-noindex", "seo-robots-root-disallowed",
    "seo-sitemap-http-error", "seo-sitemap-invalid",
})

#: Top-level names and suffixes that only ever mean "this machine or its LAN".
_LOCAL_SUFFIXES = (".local", ".localhost", ".test", ".internal", ".lan",
                   ".home.arpa", ".localdomain")


def host_of(url: str) -> str:
    host = (urlsplit(url or "").hostname or "").lower()
    return host.rstrip(".")


def is_local_host(host: str) -> bool:
    """Is this a name or an address that only resolves on a developer's network?

    `localhost`, the reserved development suffixes (`.local` from Local and
    mDNS, `.test` from RFC 2606, `.localhost`, `.internal`, `.lan`), a name with
    no dot at all (a Docker service, `http://shop`), and loopback, private or
    link-local addresses. A public name is never local, whatever it is called.
    """
    host = (host or "").lower().rstrip(".")
    if not host:
        return False
    if host == "localhost" or host.endswith(_LOCAL_SUFFIXES):
        return True
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return "." not in host
    return address.is_loopback or address.is_private or address.is_link_local


def is_local_url(url: str) -> bool:
    return is_local_host(host_of(url))


def apply(result, include: bool = False) -> dict:
    """Leave the environment findings out of a web audit of a local site.

    Mutates `result` and returns what it did, which is also stored as
    `result.environment`: `{"local": bool, "included": bool, "hidden": n,
    "by_rule": {rule: n}, "hosts": [...]}`. With `include=True` nothing is
    removed and the same counts say what *would* have been.

    Decided per finding, by the host of the page it is about, so a crawl that
    mixes a local site with a public one (a link out is not crawled, but a
    redirect can be) hides only what belongs to the local half.
    """
    by_rule: dict = {}
    hosts: set = set()
    hidden = 0
    for document in result.documents:
        if not document.issues:
            continue
        kept = []
        for issue in document.issues:
            host = host_of(issue.source or document.source)
            if issue.rule_id in LOCAL_ONLY_RULES and is_local_host(host):
                hosts.add(host)
                by_rule[issue.rule_id] = by_rule.get(issue.rule_id, 0) + 1
                hidden += 1
                if include:
                    kept.append(issue)
                continue
            kept.append(issue)
        document.issues = kept
    summary = {"local": bool(hidden) or is_local_url(getattr(result, "root", "")),
               "included": bool(include), "hidden": 0 if include else hidden,
               "would_hide": hidden, "by_rule": dict(sorted(by_rule.items())),
               "hosts": sorted(hosts)}
    result.environment = summary
    return summary
