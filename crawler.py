"""Same-domain page crawler with a configurable link-depth limit.

Depth semantics:
  depth=0  -> only the given URL is fetched.
  depth=1  -> the given URL plus every same-domain page it links to.
  depth=N  -> follow links N hops away from the root URL.

Only same-domain links are followed so the crawl can't wander off the
target site. A hard page-count cap protects against accidentally crawling
a huge site.

## Why a page can come back empty

This crawler makes one plain HTTP request per page and reads the HTML that
comes back. It runs no JavaScript — there is no browser in the loop, by
design: rendering every page would turn a fast scan into a slow one and
pull a headless browser into the dependency list. The cost of that choice
is that several very different situations all end in "no text found", and
telling them apart is not something the user can do by looking at an empty
list.

So every page carries a `PageDiagnostics` record explaining which of these
happened:

* `js-rendered` — the response is an application shell (`<div id="root">`
  and a bundle) and the copy is written into the DOM by the browser. This
  is the single most common cause, and nothing here can fix it; the honest
  answer is "point the scanner at the rendered HTML, or at the repository
  that produces it" (repository mode exists partly for this).
* `blocked` — the server answered, but with a bot check or a consent wall
  rather than the page. Detectable by status code, or by a body that is all
  markup and no copy.
* `not-html` — a PDF, an image, a JSON endpoint. Previously these vanished
  from the result list entirely, which read as "crawled, nothing found".
* `too-short` — real copy was extracted, but every block was under
  `MIN_BLOCK_LEN`. Common on navigation-only pages and link hubs.
* `no-text` — the markup genuinely has no text nodes worth reading.
* `error` — the request failed outright (DNS, TLS, timeout, 5xx).

Text extraction itself also gained a fallback: copy that sits directly in a
`<div>` or `<section>`, with no paragraph tag around it, used to be missed
entirely because those tags aren't in `CANDIDATE_TAGS` — and adding them as
ordinary candidates would capture every wrapper element's concatenated
text. `_leaf_container_blocks` picks up only containers whose own direct
text is the copy, which keeps the wrappers out.
"""
from __future__ import annotations

import re
import uuid
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from http.cookiejar import DefaultCookiePolicy, eff_request_host
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString

from lang_detect import guess_language_safe
import applog
from models import LinkRef, PageDiagnostics, PageResult, TextBlock
from text_extraction import RenderedHTML, normalize_with_map, text_from_nodes

USER_AGENT = "AIContentScanner/0.1 (+https://example.local)"

# Tags whose text content is never "content" a visitor reads.
SKIP_TAGS = {
    "script", "style", "noscript", "template", "svg", "path", "iframe",
    "head", "meta", "link",
}

# Minimum visible-text length (characters) for a block to be worth analysing.
MIN_BLOCK_LEN = 20

# Diagnostic reason codes; the UI maps each to a translated sentence.
EMPTY_JS_RENDERED = "js-rendered"
EMPTY_BLOCKED = "blocked"
EMPTY_NOT_HTML = "not-html"
EMPTY_TOO_SHORT = "too-short"
EMPTY_NO_TEXT = "no-text"
EMPTY_REDIRECTED = "redirected"
# The redirect landed on a page this crawl has already read. Recorded
# rather than dropped: a URL that vanishes from the report is
# indistinguishable from one nobody tried.
EMPTY_ALREADY_SEEN = "already-seen"
EMPTY_ERROR = "error"
# The response was larger than `CrawlConfig.max_page_bytes`, so it was not
# read at all (P-11): one page must not be able to take the whole memory.
EMPTY_TOO_LARGE = "too-large"

# Markers that identify a client-rendered application shell. Matched against
# the raw HTML, so they work whether or not the framework left a comment.
_FRAMEWORK_MARKERS = (
    ("next", re.compile(r"__NEXT_DATA__|/_next/static", re.IGNORECASE)),
    ("nuxt", re.compile(r"__NUXT__|/_nuxt/", re.IGNORECASE)),
    ("sveltekit", re.compile(r"__sveltekit|/_app/immutable", re.IGNORECASE)),
    ("angular", re.compile(r"<app-root|ng-version=", re.IGNORECASE)),
    ("vue", re.compile(r"data-v-app|id=[\"']app[\"'][^>]*>\s*</div>", re.IGNORECASE)),
    ("react", re.compile(r"id=[\"'](root|__next)[\"']", re.IGNORECASE)),
)

# Status codes that mean "the server refused to show you the page" rather
# than "the page has no text". 403 and 429 are the usual bot-check answers;
# 401 is an auth wall.
_BLOCKED_STATUSES = {401, 403, 405, 429}

_TAG_RE = re.compile(r"<[^>]+>")


#: When to hand a page to a browser instead of reading the fetch.
#:
#: `never` is the historical behaviour and the fast one. `always` renders every
#: page. `auto` is the useful default: fetch first, and render only the pages
#: whose fetch came back as an application shell - which is exactly the case
#: the diagnostics already detect and could previously only report.
RENDER_NEVER = "never"
RENDER_AUTO = "auto"
RENDER_ALWAYS = "always"

#: Recorded on a page whose text and links came from a browser, not the fetch.
#: Kept as a reason rather than a silent substitution: "this page had to be
#: rendered to be read" is a fact about the site worth showing.
RENDERED = "rendered"


@dataclass
class CrawlConfig:
    max_depth: int = 1
    max_pages: int = 30
    timeout: float = 10.0
    render_timeout: float = 30.0
    same_domain_only: bool = True
    render_mode: str = RENDER_NEVER
    #: Scoped cookie records from a session the person signed in themselves.
    #:
    #: Two clients read one site: this fetcher and, when rendering, a browser.
    #: They share no storage, so a sign-in performed in the browser leaves
    #: this half looking at the login form - the two halves of one run
    #: disagreeing about who is asking. See `site_session`; the values are
    #: never logged and never reach a report.
    cookies: list = field(default_factory=list)
    #: Ceilings that keep one hostile or broken site from exhausting memory
    #: (P-11). A real page is well under a megabyte of HTML; ten is generous
    #: and still a ceiling. 0 switches a ceiling off.
    max_page_bytes: int = 10 * 1024 * 1024
    #: Links queued from a single page. A sitemap-like page can carry
    #: thousands; the walk only ever reads `max_pages` of them.
    max_links_per_page: int = 1000
    #: Addresses waiting in the queue at once.
    max_queue: int = 20_000


class _TooLarge(Exception):
    """The body went past `max_page_bytes`."""


def _read_html(resp, limit: int) -> str:
    """The response body as text, read no further than `limit` bytes.

    Streamed and counted as it arrives, because `Content-Length` is a claim
    the server may leave out or get wrong. The bytes are then handed back to
    `requests` so the text is decoded exactly as `resp.text` always decoded
    it - the same charset rules, the same fallback.
    """
    length = (resp.headers or {}).get("Content-Length", "")
    if limit and str(length).isdigit() and int(length) > limit:
        raise _TooLarge
    iter_content = getattr(resp, "iter_content", None)
    if iter_content is None:
        # A stand-in response with the text already in hand.
        text = resp.text
        if limit and len(text) > limit:
            raise _TooLarge
        return text
    chunks: list[bytes] = []
    size = 0
    for chunk in iter_content(64 * 1024):
        size += len(chunk)
        if limit and size > limit:
            raise _TooLarge
        chunks.append(chunk)
    resp._content = b"".join(chunks)
    resp._content_consumed = True
    return resp.text


def _close(resp) -> None:
    close = getattr(resp, "close", None)
    if close is not None:
        try:
            close()
        except Exception:  # noqa: BLE001 - closing is best effort
            pass


def _session_cookie_records(cookies, root_url: str) -> list[dict]:
    """Normalize scoped records and the former ``{name: value}`` API."""
    root_host = (urlparse(root_url).hostname or "").lower()
    if isinstance(cookies, Mapping):
        values = ({
            "name": name,
            "value": value,
            "domain": root_host,
            "path": "/",
            "host_only": True,
        } for name, value in cookies.items())
    else:
        values = cookies or ()
    records = []
    for value in values:
        if not isinstance(value, Mapping):
            continue
        name = str(value.get("name") or "")
        domain = str(value.get("domain") or root_host).strip().lower()
        if not name or not domain:
            continue
        records.append({
            "name": name,
            "value": str(value.get("value") or ""),
            "domain": domain,
            "path": str(value.get("path") or "/"),
            "secure": bool(value.get("secure", False)),
            "expires": value.get("expires"),
            "host_only": bool(value.get(
                "host_only", not domain.startswith("."))),
            "rest": {
                "HttpOnly": bool(value.get("http_only", False)),
                "SameSite": str(value.get("same_site") or "Default"),
            },
        })
    return records


class _BrowserCookiePolicy(DefaultCookiePolicy):
    """CookieJar policy with RFC 6265 host-only semantics.

    Python's legacy Netscape policy accepts a non-domain cookie for child
    hosts. Browsers do not: a host-only cookie for ``example.com`` must not
    be sent to ``sub.example.com``.
    """

    def return_ok_domain(self, cookie, request) -> bool:
        _request_host, effective_host = eff_request_host(request)
        if (not cookie.domain_specified
                and cookie.domain.lower() != effective_host.lower()):
            return False
        return super().return_ok_domain(cookie, request)


def _http_session(config: CrawlConfig, root_url: str):
    """A Requests session whose signed-in cookies keep their browser scope."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    jar = getattr(session, "cookies", None)
    if hasattr(jar, "set_policy"):
        jar.set_policy(_BrowserCookiePolicy())
        original_prepare = session.prepare_request

        def prepare_request(request):
            prepared = original_prepare(request)
            # Requests builds a fresh jar with the default policy here.
            # Restore the browser policy before generating the header. The
            # jar is copied into redirected requests, so every hop repeats it.
            prepared._cookies.set_policy(jar.get_policy())
            prepared.headers.pop("Cookie", None)
            prepared.prepare_cookies(prepared._cookies)
            return prepared

        session.prepare_request = prepare_request
    for record in _session_cookie_records(config.cookies, root_url):
        if jar is None:
            continue
        cookie = jar.set(
            record["name"], record["value"], domain=record["domain"],
            path=record["path"], secure=record["secure"],
            expires=record["expires"], rest=record["rest"])
        if cookie is not None and record["host_only"]:
            # ``RequestsCookieJar.set(domain=...)`` otherwise turns a
            # host-only browser cookie into a domain cookie.
            cookie.domain_specified = False
            cookie.domain_initial_dot = False
    return session


def http_session(config: CrawlConfig, root_url: str):
    """A Requests session carrying `config.cookies` with their browser scope.

    The public name for every reader of a signed-in site - the crawl itself
    and `sharepoint_tree` - so both send the same cookies to the same hosts.
    """
    return _http_session(config, root_url)


def _scope_key(path: str) -> str:
    from urllib.parse import unquote

    path = unquote(path or "/")
    if len(path) > 1:
        path = path.rstrip("/")
    return path.casefold()


def in_site_scope(url: str, site_scope: str) -> bool:
    """Is `url` inside the path `site_scope` (`/sites/x`), ignoring case?

    Segment-aware: `/sites/x2` is not inside `/sites/x`. SharePoint paths
    are case-insensitive, so `/SITES/X/page.aspx` is.
    """
    if not site_scope:
        return True
    scope = _scope_key(site_scope)
    if scope in ("", "/"):
        return True
    key = _scope_key(urlparse(url).path)
    return key == scope or key.startswith(scope + "/")


def _normalize(url: str) -> str:
    parsed = urlparse(url)
    # Drop fragments; keep query since some sites route content via query params.
    # Collapse a trailing slash so `/about/` and `/about` dedupe into one page;
    # the root keeps its slash so `https://site` and `https://site/` also meet.
    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return parsed._replace(path=path, fragment="").geturl()


def _host_key(url: str) -> str:
    """The host, in the form two URLs can be compared by.

    Case and the default port are noise; `www.` is the part that matters. A
    site that redirects its apex to `www` links to itself under both names, and
    comparing `netloc` literally made those two names two different sites - so
    a crawl that started at the apex followed nothing at all, and the emptiness
    looked like a site without links.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = parsed.port
    default = {"http": 80, "https": 443}.get(parsed.scheme, None)
    if port and port != default:
        return f"{host}:{port}"
    return host


def _same_domain(a: str, b: str) -> bool:
    return _host_key(a) == _host_key(b)


def _should_render(mode: str, diagnostics) -> bool:
    """Is this page worth handing to a browser?"""
    if mode == RENDER_ALWAYS:
        return True
    if mode != RENDER_AUTO:
        return False
    # Exactly the cases where reading the fetch produced nothing to read. A
    # page that came back with its copy in it is not rendered again: it would
    # cost seconds per page to confirm what is already known.
    return (EMPTY_JS_RENDERED in diagnostics.reasons
            or not diagnostics.blocks_kept
            or diagnostics.extraction.get("style_blocks") == 0)


def _render_within(render, url: str, timeout: float) -> str:
    """Render one page, bounded by `timeout` seconds where the renderer can be.

    The bound used to be `SIGALRM`, which has two holes and both were silent,
    because the `except` around the call swallowed what they raised:
    Windows has no `SIGALRM` at all (`AttributeError`), and `signal.signal`
    from any thread but the main one raises `ValueError` - the window crawls
    on a worker. Either way `render` was never called and a JavaScript page
    was reported as empty.

    A signal could not have been the right tool anyway: the renderer is
    QtWebEngine, which runs on the thread that called it and must not be
    interrupted from outside. So the deadline is handed to the renderer,
    which stops its own page load at the next turn of its event loop
    (`audit.driver.html_renderer`). A plain `render(url)` callable - a test
    double, a custom renderer - is called without one: nothing in the same
    thread can stop it portably, and calling it unbounded beats not calling
    it at all.
    """
    import inspect

    try:
        parameters = inspect.signature(render).parameters.values()
    except (TypeError, ValueError):
        parameters = ()
    if any(p.name == "timeout" or p.kind is inspect.Parameter.VAR_KEYWORD
           for p in parameters):
        return render(url, timeout=timeout) or ""
    return render(url) or ""


CANDIDATE_TAGS = [
    "h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "a", "button",
    "span", "figcaption", "blockquote", "td", "th", "label",
]

# Containers that often hold copy directly, with no paragraph tag inside.
# Only their *own* text nodes are read (see `_leaf_container_blocks`), never
# the concatenation of their children — otherwise a page wrapper would come
# back as one enormous "block" containing the whole page.
CONTAINER_TAGS = ["div", "section", "article", "dd", "dt", "figure", "summary", "caption"]


def _extract_text_blocks(html: str, page_url: str,
                          diagnostics: PageDiagnostics | None = None) -> list[TextBlock]:
    if isinstance(html, RenderedHTML) and isinstance(html.text_snapshot.get("blocks"), list):
        return _snapshot_blocks(html.text_snapshot, page_url, diagnostics)
    soup = BeautifulSoup(html, "html.parser")
    blocks: list[TextBlock] = []
    dropped_short = 0
    dropped_dup = 0
    hidden = 0

    # Walk block-level-ish containers so each highlighted chunk maps to a
    # coherent piece of UI copy (heading, paragraph, button label, list item...)
    candidates = soup.find_all(CANDIDATE_TAGS)

    # Normalized text per candidate, computed exactly once. The previous
    # version rebuilt each ancestor's text with a fresh stripped_strings
    # join inside the per-candidate loop, which re-walked the same subtrees
    # over and over on deep pages.
    texts: dict[int, str] = {}
    nodes_by_tag = {}
    for tag in candidates:
        nodes = _text_nodes(tag)
        nodes_by_tag[id(tag)] = nodes
        texts[id(tag)] = text_from_nodes(nodes)[0]

    for tag in candidates:
        text = texts[id(tag)]
        if tag.find_parent(SKIP_TAGS):
            continue
        if _static_hidden(tag):
            hidden += 1
            continue
        if len(normalize_with_map(text)[0]) < MIN_BLOCK_LEN:
            if text:
                dropped_short += 1
            else:
                continue

        # Skip a node when an ancestor candidate carries exactly the same
        # text (e.g. <li><a>same words</a></li> would otherwise be captured
        # twice). Deliberately identity-based: two *separate* elements that
        # happen to share wording are both kept, because the user needs to
        # review and fix every occurrence on the page, not just the first.
        parent_dup = False
        for parent in tag.parents:
            parent_text = texts.get(id(parent))
            if parent_text is not None and parent_text == text:
                parent_dup = True
                break
        if parent_dup:
            dropped_dup += 1
            continue

        blocks.append(_make_block(tag, text, page_url, nodes=nodes_by_tag[id(tag)]))

    covered = {id(tag) for tag in candidates}
    extra, extra_short = _leaf_container_blocks(soup, page_url, covered)
    blocks.extend(extra)
    dropped_short += extra_short
    attributes = _attribute_blocks(soup, page_url)
    blocks.extend(attributes)

    if diagnostics is not None:
        diagnostics.candidates_found = len(candidates)
        diagnostics.blocks_kept = len(blocks)
        diagnostics.dropped_too_short = dropped_short
        diagnostics.dropped_duplicate = dropped_dup
        diagnostics.extraction = {
            "mode": "static", "blocks": len(blocks), "hidden_excluded": hidden,
            "style_blocks": sum(b.analysis_eligible for b in blocks),
            "visibility_unknown": len(blocks), "attribute_blocks": len(attributes),
            "frames": [{"selector": _dom_path(tag), "status": "unknown", "reason": "browser required"}
                       for tag in soup.find_all("iframe")],
            "closed_shadow_roots": "unknown", "truncated": False,
        }
        if isinstance(html, RenderedHTML) and html.text_snapshot.get("error"):
            diagnostics.extraction["snapshot_error"] = str(html.text_snapshot["error"])
    return blocks


def _snapshot_blocks(snapshot, page_url, diagnostics):
    blocks, short, duplicate = [], 0, 0
    seen = set()
    for entry in snapshot.get("blocks", []):
        nodes = entry.get("nodes", [])
        if not nodes:
            continue
        text, ranges, languages = text_from_nodes(nodes)
        normal, mapping = normalize_with_map(text)
        declared = {r["language"] for r in languages}
        attribute = entry.get("attribute", "")
        if not text:
            continue
        if len(normal) < MIN_BLOCK_LEN:
            short += 1
        identity = (entry["selector"], attribute, text,
                    repr(entry.get("context_path", [])))
        if identity in seen:
            duplicate += 1
            continue
        seen.add(identity)
        blocks.append(TextBlock(
            block_id=str(uuid.uuid4()), page_url=page_url, dom_path=entry["selector"],
            text=text, raw_text=text, normalized_text=normal, normalization_map=mapping,
            language_hint=guess_language_safe(text), visibility=entry.get("visibility", "unknown"),
            declared_language=(next(iter(declared)) if len(declared) == 1 else "mixed" if declared
                               else entry.get("declared_language")), language_context=languages,
            rendered_visible_text=entry.get("rendered_visible_text"), dom_ranges=ranges,
            attribute_name=attribute, text_kind=entry.get("text_kind", "dom-text"),
            context_path=entry.get("context_path", []), source_context=entry.get("source_context", {}),
            analysis_eligible=len(normal) >= MIN_BLOCK_LEN,
        ))
    if diagnostics is not None:
        diagnostics.candidates_found = len(snapshot.get("blocks", []))
        diagnostics.blocks_kept = len(blocks)
        diagnostics.dropped_too_short = short
        diagnostics.dropped_duplicate = duplicate
        diagnostics.extraction = {k: v for k, v in snapshot.items() if k != "blocks"}
        diagnostics.extraction.update(mode="rendered", blocks=len(blocks),
            style_blocks=sum(b.analysis_eligible for b in blocks),
            visibility_unknown=sum(b.visibility != "visible" for b in blocks))
    return blocks


def _leaf_container_blocks(soup, page_url: str, covered: set) -> tuple[list[TextBlock], int]:
    """Copy sitting directly inside a `<div>`/`<section>`/... with no inner
    tag of its own — `<div class="lead">Some sentence.</div>`.

    Only the container's *direct* text children are read, and only when the
    container has no candidate descendant already carrying that text, so a
    page-level wrapper never turns into one giant block.
    """
    blocks: list[TextBlock] = []
    dropped_short = 0
    for tag in soup.find_all(CONTAINER_TAGS):
        if tag.find_parent(SKIP_TAGS) or _static_hidden(tag):
            continue
        nodes = _text_nodes(tag, direct=True)
        own_text = text_from_nodes(nodes)[0]
        if not own_text:
            continue
        if len(normalize_with_map(own_text)[0]) < MIN_BLOCK_LEN:
            dropped_short += 1
        if id(tag) in covered:
            continue
        blocks.append(_make_block(tag, own_text, page_url, nodes=nodes))
    return blocks, dropped_short


def _make_block(tag, text: str, page_url: str, *, nodes=None, attribute="") -> TextBlock:
    normalized, mapping = normalize_with_map(text)
    ranges, languages = (text_from_nodes(nodes)[1:] if nodes else ([], []))
    declared = {r["language"] for r in languages}
    if not declared:
        inherited = _declared_language(tag)
        declared = {inherited} if inherited else set()
    return TextBlock(
        block_id=str(uuid.uuid4()),
        page_url=page_url,
        dom_path=_dom_path(tag),
        text=text,
        # Tagged here so a rewrite request can tell the model which language
        # to answer in. `guess_language_safe`, not `guess_language`: the
        # difference is what happens to a string too short to read. The
        # unsafe one answers "en", which is a fallback wearing the clothes of
        # a reading, and it is what every consumer downstream then believes.
        # Measured 2026-08-31 on a live Italian page: 29 of 71 blocks were
        # tagged `en` while `guess_language_safe` said `None`, so short
        # Italian strings were judged by the English cliché list and would
        # have been handed to the rewrite provider as English. `None` is the
        # honest answer and the one every consumer already knows how to
        # handle - the detectors check every list, and `prompt_language`
        # names no language rather than the wrong one.
        language_hint=guess_language_safe(text),
        raw_text=text, normalized_text=normalized, normalization_map=mapping,
        visibility="unknown", attribute_name=attribute,
        text_kind="attribute" if attribute else "dom-text",
        dom_ranges=ranges, language_context=languages,
        declared_language=next(iter(declared)) if len(declared) == 1 else "mixed" if declared else None,
        analysis_eligible=len(normalized) >= MIN_BLOCK_LEN,
        source_context={key: value for key, value in {
            "element": tag.name,
            "locale_key": tag.get("data-i18n") or tag.get("data-l10n-key"),
            "component_file": tag.get("data-component-file"),
        }.items() if isinstance(value, str) and value},
    )


def _declared_language(tag):
    for node in [tag, *tag.parents]:
        value = node.get("lang") or node.get("xml:lang")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _static_hidden(tag):
    """Known visual exclusions only; aria-hidden does not hide pixels."""
    visibility_set = False
    for node in [tag, *tag.parents]:
        if node.has_attr("hidden"):
            return True
        style = node.get("style") or ""
        if not isinstance(style, str):
            continue
        declarations = {}
        for part in style.lower().split(";"):
            name, colon, value = part.partition(":")
            if colon:
                declarations[name.strip()] = value.split("!important", 1)[0].strip()
        if declarations.get("display") == "none" or declarations.get("content-visibility") == "hidden":
            return True
        if declarations.get("opacity") in ("0", "0.0", "0%"):
            return True
        visibility = declarations.get("visibility")
        if not visibility_set and visibility in ("visible", "hidden", "collapse"):
            visibility_set = True
            if visibility != "visible":
                return True
    return False


def _text_nodes(tag, *, direct=False):
    from bs4 import Comment
    nodes = []
    for child in (tag.children if direct else tag.descendants):
        if not isinstance(child, NavigableString) or isinstance(child, Comment):
            continue
        parent = child.parent
        if parent is None or parent.name in SKIP_TAGS or parent.find_parent(SKIP_TAGS) or _static_hidden(parent):
            continue
        index = next(i for i, sibling in enumerate(parent.children) if sibling is child)
        nodes.append({"text": str(child), "selector": _dom_path(parent), "node_index": index,
                      "language": _declared_language(parent)})
    return nodes


def _attribute_blocks(soup, page_url):
    blocks = []
    for tag in soup.find_all(True):
        attribute_skip = SKIP_TAGS - {"svg", "path"}
        if tag.name in attribute_skip or tag.find_parent(attribute_skip) or _static_hidden(tag):
            continue
        for attribute in ("aria-label", "placeholder", "alt", "title"):
            text = tag.get(attribute)
            if isinstance(text, str) and text.strip():
                blocks.append(_make_block(tag, text, page_url, attribute=attribute))
        for reference in str(tag.get("aria-labelledby") or "").split():
            labels = soup.find_all(id=reference)
            if len(labels) != 1:
                continue
            # Referenced labels may deliberately be visually hidden.
            text = labels[0].get_text().strip()
            if text:
                block = _make_block(tag, text, page_url, attribute="aria-labelledby")
                block.text_kind = "referenced-label"
                block.source_context["label_reference"] = reference
                blocks.append(block)
    return blocks


def _dom_path(tag) -> str:
    """Build a CSS selector for `tag`.

    Sibling position is found by identity (`is`), not by list.index(): bs4
    Tags compare equal by *content*, so index() would return the position
    of the first same-named sibling with matching markup and silently
    produce a selector pointing at the wrong element.
    """
    parts = []
    node = tag
    while node is not None and getattr(node, "name", None) not in (None, "[document]"):
        idx = 1
        if node.parent is not None:
            siblings = node.parent.find_all(node.name, recursive=False)
            for i, sibling in enumerate(siblings):
                if sibling is node:
                    idx = i + 1
                    break
        parts.append(f"{node.name}:nth-of-type({idx})")
        node = node.parent
    return " > ".join(reversed(parts))


def _find_links(html: str, page_url: str) -> list[LinkRef]:
    """Every anchor worth following, read in one pass.

    Returns records rather than bare addresses because two passes want this
    list: the walk, which needs where to go next, and `audit.crawlability`,
    which needs to quote the anchor that reached a failure. It used to return
    strings, so the audit parsed the same markup a second time to get the
    element back.
    """
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        links.append(LinkRef(href=href,
                             url=_normalize(urljoin(page_url, href)),
                             snippet=str(a)[:300]))
    return links


# ------------------------------------------------------------- diagnostics

def _detect_framework(html: str) -> str:
    for name, pattern in _FRAMEWORK_MARKERS:
        if pattern.search(html):
            return name
    return ""


def _text_ratio(html: str) -> float:
    """Share of the response that is visible text rather than markup. An
    application shell sits near zero; a content page is typically well
    above 0.1."""
    if not html:
        return 0.0
    stripped = _TAG_RE.sub(" ", html)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return len(stripped) / len(html)


def _diagnose(diag: PageDiagnostics, url: str, html: str, blocks: list) -> None:
    """Fill in `diag.reasons` — only meaningful when nothing was extracted,
    but the measurements are recorded either way so a thin page can be
    explained too."""
    diag.html_bytes = len(html)
    diag.text_ratio = round(_text_ratio(html), 4)
    diag.js_framework = _detect_framework(html)
    diag.has_noscript_notice = "<noscript" in html.lower()

    if (diag.final_url and _normalize(diag.final_url) != _normalize(url)
            and EMPTY_REDIRECTED not in diag.reasons):
        diag.reasons.append(EMPTY_REDIRECTED)
    if any(getattr(block, "analysis_eligible", True) for block in blocks):
        return

    if diag.status_code in _BLOCKED_STATUSES:
        diag.reasons.append(EMPTY_BLOCKED)
    if diag.js_framework or (diag.text_ratio < 0.05 and diag.html_bytes > 500):
        diag.reasons.append(EMPTY_JS_RENDERED)
    elif diag.dropped_too_short:
        diag.reasons.append(EMPTY_TOO_SHORT)
    elif not diag.candidates_found or diag.text_ratio < 0.01:
        diag.reasons.append(EMPTY_NO_TEXT)
    else:
        diag.reasons.append(EMPTY_TOO_SHORT)


def page_from_html(html: str, url: str, depth: int = 0) -> PageResult:
    """One page's worth of result, built from HTML somebody else obtained.

    The crawl is the usual way to get HTML, but not the only one: a single
    local file opened in a browser has no crawl to be part of - there is one
    document, already rendered, and `requests` cannot even fetch it (it does
    not speak `file://`). Extracting and diagnosing it still has to happen the
    same way, so that path is this function rather than a second copy of the
    body of `crawl`.
    """
    diagnostics = PageDiagnostics()
    diagnostics.final_url = url
    diagnostics.html_bytes = len(html or "")
    diagnostics.reasons = [RENDERED]
    blocks = _extract_text_blocks(html or "", url, diagnostics)
    _diagnose(diagnostics, url, html or "", blocks)
    return PageResult(url=url, depth=depth, blocks=blocks, raw_html=html,
                      diagnostics=diagnostics,
                      links=_find_links(html or "", url))


def crawl(root_url: str, config: CrawlConfig | None = None, progress_cb=None,
          render=None, walk=None, cancelled=None, seeds=None,
          site_scope: str | None = None) -> list[PageResult]:
    """Breadth-first crawl starting at root_url up to config.max_depth hops.

    progress_cb, if given, is called as progress_cb(url, depth) right before
    each page is fetched, so a UI can show live progress.

    render, if given, is called as render(url) and returns the DOM a browser
    built, or "" when it could not. It is injected rather than imported so the
    crawler keeps no opinion about which browser, and stays importable without
    Qt: the walk is the crawler's job, and rendering is one way of reading a
    page. `config.render_mode` decides when it is called at all.

    walk, if given, is a `models.CrawlDiagnostics` filled in as the crawl
    ends. Passed in rather than returned so every existing caller keeps
    working unchanged - the same shape `PageDiagnostics` already uses. What
    it records is what the crawl did *not* reach: one that stopped at its
    page limit leaves a queue behind, and once the results are a list of
    `PageResult` those addresses are gone. "30 pages, no findings" then
    reads as a verdict on the site rather than on the thirty.

    Named `walk` and not `diagnostics` for a reason worth keeping: the loop
    below binds `diagnostics` to a fresh `PageDiagnostics` on every page, so
    a parameter of that name is shadowed by the first iteration. It was, and
    the end-of-crawl numbers went onto the last page's diagnostics instead -
    silently, because both objects take an attribute assignment happily.

    cancelled, when supplied, is a zero-argument callable checked between
    pages, network responses and browser renders. It cannot interrupt a
    socket inside `requests`, but it prevents the next expensive unit from
    starting and gives every UI surface one cooperative stop contract.

    seeds, when given, is the list of pages to read instead of a walk: every
    seed is read at depth 0 and no link found on a page is followed. The
    list comes from somewhere that knows the site's pages better than its
    links do (`sharepoint_tree`). `max_pages` still applies, and what it left
    unread is in `walk.queued_when_stopped` like any other stopped crawl.

    site_scope, when given, is a path (`/sites/x`) the crawl stays inside,
    compared without case and by whole segments. An address outside it is
    neither fetched nor queued, and the distinct addresses turned away are
    counted in `walk.out_of_scope`: one host serves a whole SharePoint
    tenant, and a link into another site is not a page of this one.
    """
    config = config or CrawlConfig()
    root_url = _normalize(root_url)

    visited: set[str] = set()
    out_of_scope: set[str] = set()
    if seeds:
        start = [(_normalize(url), 0) for url in dict.fromkeys(seeds)]
    else:
        start = [(root_url, 0)]
    queue: deque[tuple[str, int]] = deque()
    for url, depth in start:
        if in_site_scope(url, site_scope):
            queue.append((url, depth))
        else:
            out_of_scope.add(url)
    #: A seeded crawl reads its list and follows nothing.
    max_depth = 0 if seeds else config.max_depth
    results: list[PageResult] = []
    session = _http_session(config, root_url)

    #: Pages actually read as HTML. The budget counts these rather than
    #: `len(results)`, because a result is also recorded for an address that
    #: turned out to be a file: a link to a `.jpg` or a `.pdf` is fetched,
    #: found not to be HTML, and kept as a diagnostic. Measured on a live
    #: WordPress site: 25 of a 250-page budget went to uploads, so the
    #: person who asked for 250 pages got 225 and no way to see why.
    pages_read = 0
    #: What stops a media-heavy site from spending the whole walk on files
    #: nobody asked for. Three fetches per page of budget: the same site had
    #: one file per ten pages, so this is far above real sites and still a
    #: ceiling. 0 (unlimited pages) keeps no ceiling either.
    fetch_ceiling = config.max_pages * 3 if config.max_pages else 0

    while queue and not (cancelled and cancelled()) \
            and (config.max_pages == 0 or pages_read < config.max_pages) \
            and (fetch_ceiling == 0 or len(results) < fetch_ceiling):
        url, depth = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        if progress_cb:
            progress_cb(url, depth)

        diagnostics = PageDiagnostics()
        resp = None
        try:
            resp = session.get(url, timeout=config.timeout, stream=True)
            if cancelled and cancelled():
                _close(resp)
                break
            diagnostics.status_code = resp.status_code
            diagnostics.final_url = resp.url
            diagnostics.content_type = resp.headers.get("Content-Type", "")
            diagnostics.headers = {k.lower(): v for k, v in resp.headers.items()}
            applog.debug("crawl.page", url=url, depth=depth,
                         status=resp.status_code,
                         type=diagnostics.content_type[:40])
            resp.raise_for_status()
            content_type = diagnostics.content_type
            if "text/html" not in content_type and not content_type.startswith("text/"):
                # Recorded rather than skipped. Dropping it silently was
                # indistinguishable from a page that was crawled and found
                # clean, which is exactly the confusion this whole
                # diagnostics path exists to remove.
                diagnostics.reasons.append(EMPTY_NOT_HTML)
                results.append(PageResult(url=url, depth=depth, diagnostics=diagnostics))
                _close(resp)
                continue
            try:
                html = _read_html(resp, config.max_page_bytes)
            except _TooLarge:
                applog.warning("crawl.page_too_large", url=url,
                               limit=config.max_page_bytes)
                diagnostics.reasons.append(EMPTY_TOO_LARGE)
                results.append(PageResult(url=url, depth=depth, diagnostics=diagnostics))
                continue
            finally:
                _close(resp)
            landing = _normalize(resp.url)
            if landing != _normalize(url):
                # Three URLs redirecting to one page are one page. Analysing
                # the landing page once per address counted the same copy
                # three times, spent three AI calls on it, and reported a
                # site larger than it is.
                diagnostics.reasons.append(EMPTY_REDIRECTED)
                if landing in visited:
                    diagnostics.reasons.append(EMPTY_ALREADY_SEEN)
                    results.append(
                        PageResult(url=url, depth=depth, diagnostics=diagnostics))
                    continue
                visited.add(landing)
                # Links on the page are relative to where it landed, not to
                # where it was asked for.
                url_base = resp.url
            else:
                url_base = url
        except requests.RequestException as exc:
            if resp is not None:
                _close(resp)
            applog.warning("crawl.page_failed", url=url, depth=depth,
                           error=f"{type(exc).__name__}: {exc}")
            diagnostics.reasons.append(EMPTY_ERROR)
            results.append(
                PageResult(url=url, depth=depth, error=str(exc), diagnostics=diagnostics)
            )
            continue

        blocks = _extract_text_blocks(html, url, diagnostics)
        _diagnose(diagnostics, url, html, blocks)

        # The page was read as it arrived. If that reading is empty because the
        # copy is written by JavaScript, the browser is the only reader that can
        # answer - and the fetch already said so.
        if (render is not None and not (cancelled and cancelled())
                and _should_render(config.render_mode, diagnostics)):
            rendered = ""
            try:
                rendered = _render_within(render, url, config.render_timeout)
            except Exception as exc:  # noqa: BLE001
                diagnostics.render_error = str(exc)
            if rendered:
                html = rendered
                diagnostics.html_bytes = len(rendered)
                # Re-diagnosed from scratch: the reasons recorded a moment ago
                # described the shell, and every one of them may now be false.
                diagnostics.reasons = [RENDERED]
                blocks = _extract_text_blocks(html, url, diagnostics)
                _diagnose(diagnostics, url, html, blocks)

        if cancelled and cancelled():
            break

        # Read once, at every depth. This used to happen only below the
        # depth ceiling, because the walk was the only reader; the audit now
        # reads the same list, and a page at the last depth has anchors that
        # matter even though nothing will be queued from them.
        links = _find_links(html, url_base)
        results.append(
            PageResult(url=url, depth=depth, blocks=blocks, raw_html=html,
                       diagnostics=diagnostics, links=links)
        )
        pages_read += 1

        if depth < max_depth:
            taken = 0
            for link in links:
                if link.url in visited:
                    continue
                if config.same_domain_only and not _same_domain(link.url, root_url):
                    continue
                if not in_site_scope(link.url, site_scope):
                    out_of_scope.add(link.url)
                    continue
                if ((config.max_links_per_page
                     and taken >= config.max_links_per_page)
                        or (config.max_queue and len(queue) >= config.max_queue)):
                    # Said once per page, not once per link: the walk goes
                    # on, it just stops widening (P-11).
                    applog.warning("crawl.links_capped", url=url,
                                   found=len(links), queued=taken,
                                   queue=len(queue))
                    break
                queue.append((link.url, depth + 1))
                taken += 1

    if walk is not None:
        walk.pages_read = pages_read
        walk.limit = config.max_pages
        # What is still queued, minus anything already visited: the queue
        # holds links as they were found, and a page linked from three
        # others is in it three times. Counting the raw length would report
        # a site three times larger than it is.
        remaining = {url for url, _depth in queue if url not in visited}
        walk.queued_when_stopped = len(remaining)
        walk.out_of_scope = len(out_of_scope)
    return results
