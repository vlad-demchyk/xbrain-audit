"""Whether what was audited is the site, or the door in front of it.

Half of what is worth checking stands behind a login: an admin area, an
account page, an intranet, a staging site under basic auth. Before this the
tool did not know that and, worse, did not say so: it fetched the login
page, found three things wrong with it, and reported them with exactly the
confidence it reports a real page with. "40 pages, 3 findings" over a site
that answered with one login form forty times is not a quiet result, it is
the wrong question answered forty times.

So this pass produces **diagnostics about the run**, never findings about
the site. A login wall is not a defect of the page - it is the reason the
page in the report is not the page anyone wanted audited.

What counts as evidence, and why each one:

* **401** always carries `WWW-Authenticate`: the server is saying *how* to
  authenticate, which makes it the only status that identifies itself. The
  scheme is named in the diagnostic, because "Basic" and "Negotiate" are
  different conversations.
* **403** carries no such header. It means "not for you", which may be a
  login wall and may be a permission - so it is recorded as the weaker
  signal it is.
* **A redirect to something that looks like a sign-in address.** The status
  is 200 and the body is real, so nothing else in the pipeline notices; the
  only trace is that the final URL is not the one that was asked for.
* **An identity provider.** A redirect that ends on Microsoft Entra ID
  (`login.microsoftonline.com` and its siblings), an Azure AD B2C tenant
  (`*.b2clogin.com`) or ADFS (`/adfs/ls`) is a sign-in by definition, and
  so are the OAuth `authorize` endpoints and SharePoint's own hops
  (`/_layouts/15/Authenticate.aspx`, `/_forms/default.aspx`). These count
  as certain: the Microsoft sign-in page is built by script and carries no
  `<input>` in its HTML, so the password-field signal never fires on it.
* **SharePoint's 403.** SharePoint Online answers a request without a
  session with `403` and `X-Forms_Based_Auth_Required` - a refusal that
  does say how to get in, so it is certain rather than the weak 403.
* **A password field.** `<input type="password">`, or a form posting to
  something with login in its name. This is the signal that catches a
  single-page app, where the address never changes at all.

**One wall, not N pages.** When the same signal answers on many addresses,
the report says that: a crawl that walked into a wall found one wall, and
listing it forty times buries the fact that forty addresses were never read.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlparse

#: The signals, weakest last. Also the translation-key stems.
HTTP_401 = "http-401"
HTTP_403 = "http-403"
LOGIN_REDIRECT = "login-redirect"
PASSWORD_FORM = "password-form"

#: Addresses that mean "sign in here". Matched on the path, so a marketing
#: page at `/why-login-matters` is not one of them, and on `returnUrl`,
#: which is how a redirect says where it will send you back to.
_LOGIN_PATH = re.compile(
    r"(^|/)(login|log-in|signin|sign-in|auth|sso|session[s]?|"
    r"account/login|users/sign_in|wp-login\.php)(/|$|\.)", re.I)
_RETURN_PARAM = re.compile(
    r"[?&](returnurl|return_to|redirect_uri|redirect_to|next|continue)=", re.I)

#: Hosts that do nothing but sign people in. The single list: anything else
#: that has to recognise a sign-in (`sharepoint_tree` among them) asks
#: `is_definite_login_url` rather than keeping its own copy.
IDENTITY_PROVIDER_HOSTS = (
    "login.microsoftonline.com",
    "login.microsoft.com",
    "login.windows.net",
    "login.live.com",
)
#: Host suffixes that are an identity provider whatever the tenant prefix.
IDENTITY_PROVIDER_SUFFIXES = (".b2clogin.com",)
#: Paths that are a sign-in step on any host: ADFS, the OAuth authorize
#: endpoints, and SharePoint's own hops towards the identity provider.
_DEFINITE_LOGIN_PATH = re.compile(
    r"(^|/)(adfs/ls|oauth2/authorize|oauth2/v2\.0/authorize|"
    r"_forms/default\.aspx|_layouts/15/authenticate\.aspx|_login|_trust)"
    r"(/|$)", re.I)
#: SharePoint's "no session" answer to a fetcher: 403 with this header.
FORMS_AUTH_HEADER = "x-forms_based_auth_required"

_PASSWORD_INPUT = re.compile(
    r"<input[^>]+type\s*=\s*[\"']?password", re.I)
_CURRENT_PASSWORD = re.compile(
    r"autocomplete\s*=\s*[\"']?current-password", re.I)
_LOGIN_FORM_ACTION = re.compile(
    r"<form[^>]+action\s*=\s*[\"'][^\"']*(login|signin|sign-in|session)", re.I)


@dataclass(frozen=True)
class Wall:
    """One address that answered with a door rather than with a page."""
    url: str
    signal: str
    #: What said so, already a string and not translated: an auth scheme, a
    #: redirect target, the form's action. It is the line a reader checks
    #: the diagnosis against.
    detail: str = ""
    #: Set when the evidence settles it even though the signal alone would
    #: not: a 403 carrying `X-Forms_Based_Auth_Required`, a redirect that
    #: ended on an identity provider. Kept beside `signal` rather than as new
    #: signals so every surface that names the signal still knows its words.
    definite: bool = False

    @property
    def certain(self) -> bool:
        """Is this a login wall, as opposed to something that may be one?

        401 and a password field are the page saying it itself. A 403 is the
        server declining without saying why, and a redirect to `/auth` may be
        an SSO hop that lands somewhere real - both are worth reporting and
        neither is proof.
        """
        return self.definite or self.signal in (HTTP_401, PASSWORD_FORM)


def is_identity_provider_host(host: str) -> bool:
    host = (host or "").lower().rstrip(".")
    if host in IDENTITY_PROVIDER_HOSTS:
        return True
    return any(host.endswith(suffix) for suffix in IDENTITY_PROVIDER_SUFFIXES)


def is_definite_login_url(url: str) -> bool:
    """Is this address a sign-in step, whatever page it is on?

    True for an identity provider's host and for the paths that exist only
    to sign someone in. Unlike `_looks_like_login_url` it never guesses from
    a word in the path, which is what lets a caller treat it as proof.
    """
    parsed = urlparse(url or "")
    if is_identity_provider_host(parsed.hostname or ""):
        return True
    return bool(_DEFINITE_LOGIN_PATH.search(parsed.path or ""))


def forms_auth_required(headers) -> bool:
    """Did SharePoint say "sign in" in the one header it uses for that?"""
    if not headers:
        return False
    try:
        items = headers.items()
    except AttributeError:
        return False
    return any(str(key).lower() == FORMS_AUTH_HEADER for key, _value in items)


def _query_keys(query: str) -> str:
    """The query with its keys percent-decoded, values dropped.

    Microsoft's sign-in redirect writes `redirect%5Furi=`: an encoded
    underscore in the key, which the pattern would otherwise never see.
    """
    keys = [key for key, _value in parse_qsl(query or "", keep_blank_values=True)]
    return "?" + "&".join(f"{key}=" for key in keys) if keys else ""


def _looks_like_login_url(url: str) -> bool:
    parsed = urlparse(url or "")
    return bool(is_definite_login_url(url)
                or _LOGIN_PATH.search(parsed.path or "")
                or _RETURN_PARAM.search(_query_keys(parsed.query)))


def _without_query(url: str) -> str:
    """Where a redirect went, without what it carried.

    An identity provider's query holds `state`, `nonce` and the return
    address: none of it is a secret on its own and none of it belongs in a
    report a person forwards.
    """
    parsed = urlparse(url or "")
    return parsed._replace(query="", fragment="").geturl()


def inspect(page) -> Wall | None:
    """The wall this page ran into, or `None` if it is a page.

    Ordered by how much the evidence settles: a 401 names its own scheme, a
    password field is the page saying what it is, a redirect is an address
    changing under the request, and a 403 is a refusal with no reason given.
    """
    diagnostics = getattr(page, "diagnostics", None)
    url = getattr(page, "url", "") or ""
    status = getattr(diagnostics, "status_code", None)
    headers = getattr(diagnostics, "headers", None) or {}
    markup = getattr(page, "raw_html", "") or ""

    if status == 401:
        scheme = (headers.get("www-authenticate") or "").split(" ")[0]
        return Wall(url, HTTP_401, scheme or "unnamed scheme")

    if forms_auth_required(headers):
        return Wall(url, HTTP_403 if status == 403 else LOGIN_REDIRECT,
                    "X-Forms_Based_Auth_Required", definite=True)

    if markup:
        if _PASSWORD_INPUT.search(markup) or _CURRENT_PASSWORD.search(markup):
            match = _LOGIN_FORM_ACTION.search(markup)
            return Wall(url, PASSWORD_FORM,
                        match.group(0)[:80] if match else "<input type=password>")

    final = getattr(diagnostics, "final_url", "") or ""
    if final and final != url and _looks_like_login_url(final):
        return Wall(url, LOGIN_REDIRECT, _without_query(final),
                    definite=is_definite_login_url(final))
    # An identity provider's page reached directly, or a crawl that followed
    # a link to one: no body check, because that page is built by script.
    if is_definite_login_url(url):
        return Wall(url, LOGIN_REDIRECT, _without_query(url), definite=True)
    # An address that *is* a login page, reached directly rather than by
    # redirect - a crawl that followed a "Sign in" link. Only when the body
    # gave nothing away, so a real page at `/account/login/help` that has no
    # password field is not called a wall on its name alone.
    if not markup and _looks_like_login_url(url):
        return Wall(url, LOGIN_REDIRECT, _without_query(url))

    if status == 403:
        return Wall(url, HTTP_403, "403 with no WWW-Authenticate")

    return None


@dataclass
class WallReport:
    """What a crawl found in front of the site, rolled up.

    `by_signal` is what makes this readable: one wall answering on forty
    addresses is one row, and the addresses are carried so nobody has to
    take the count on trust.
    """
    walls: list = field(default_factory=list)
    pages_read: int = 0

    @property
    def blocked(self) -> int:
        return len(self.walls)

    @property
    def certain(self) -> bool:
        return any(wall.certain for wall in self.walls)

    def by_signal(self) -> dict:
        grouped: dict = {}
        for wall in self.walls:
            grouped.setdefault(wall.signal, []).append(wall)
        return grouped

    @property
    def whole_site(self) -> bool:
        """Was *everything* the crawl reached a door?

        The case that matters most, and the one a count alone hides: a run
        that read nothing but login pages has audited nothing, and its clean
        summary is the most misleading output this tool can produce.
        """
        return bool(self.walls) and self.blocked >= self.pages_read


def scan(pages) -> WallReport:
    """Every wall in a crawl's results, with what was read alongside."""
    report = WallReport()
    for page in pages or ():
        report.pages_read += 1
        wall = inspect(page)
        if wall is not None:
            report.walls.append(wall)
    return report
