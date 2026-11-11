"""SharePoint page-tree discovery, against canned REST responses.

No live tenant: every response is a fixture under
`tests/fixtures/sharepoint_tree/` or an inline dict, and time is injected so
throttling waits are recorded instead of slept.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote

import pytest

import sharepoint_tree as spt

FIXTURES = Path(__file__).parent / "fixtures" / "sharepoint_tree"
SITE = "https://contoso.sharepoint.com/sites/Portal"
EMPTY = {"value": []}


def fx(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None, text=None):
        self.status_code = status
        self._body = body
        self.headers = dict(headers or {})
        self.text = text if text is not None else (
            json.dumps(body) if body is not None else "")

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def not_found(message="List does not exist."):
    return FakeResponse(404, {"odata.error": {"code": "-1",
                                              "message": {"value": message}}})


class FakeSession:
    """Routes a GET by regex over the decoded URL; first match wins.

    A route's response may be a list, consumed one per call (the last one
    repeats), so a 429 followed by a 200 is two entries.
    """

    def __init__(self, routes):
        self.routes = [(re.compile(p), r) for p, r in routes]
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, headers=None, timeout=None, allow_redirects=True):
        decoded = unquote(url)
        self.calls.append((decoded, dict(headers or {})))
        for pattern, response in self.routes:
            if pattern.search(decoded):
                if isinstance(response, list):
                    item = response.pop(0) if len(response) > 1 else response[0]
                else:
                    item = response
                if isinstance(item, FakeResponse):
                    return item
                return FakeResponse(200, item)
        return not_found("no route")

    def urls(self):
        return [u for u, _h in self.calls]


class FakeTime:
    def __init__(self):
        self.now = 1000.0
        self.slept: list[float] = []

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds

    def clock(self):
        return self.now

    def wall(self):
        return 1_800_000_000.0 + self.now


def run(session, **kwargs):
    t = kwargs.pop("time", None) or FakeTime()
    kwargs.setdefault("min_interval", 0)
    tree = spt.discover(kwargs.pop("site", SITE), session, sleep=t.sleep,
                        clock=t.clock, wall_clock=t.wall, **kwargs)
    return tree, t


def full_site_routes():
    return [
        (r"/sites/Portal/_api/web\?\$select", fx("web.json")),
        (r"/sites/Portal/Rischi/_api/web/webs", fx("webs_sub.json")),
        (r"/sites/Portal/_api/web/webs", fx("webs_root.json")),
        (r"/_api/web/rootfolder", {"WelcomePage": "SitePages/Home.aspx"}),
        (r"/Rischi/_api/web/GetList\('/sites/Portal/Rischi/SitePages'\)/items",
         fx("sub_sitepages.json")),
        (r"/Rischi/_api/web/lists\?", {"value": [{"RootFolder": {
            "ServerRelativeUrl": "/sites/Portal/Rischi/SitePages"}}]}),
        (r"GetList\('/sites/Portal/SitePages'\)/items\?\$skiptoken",
         fx("sitepages_2.json")),
        (r"GetList\('/sites/Portal/SitePages'\)/items\?\$select",
         fx("sitepages_1.json")),
        (r"/sites/Portal/_api/web/lists\?", fx("page_libraries.json")),
        (r"/sites/Portal/_api/web/navigation/QuickLaunch", fx("quicklaunch.json")),
        (r"/_api/web/navigation/", EMPTY),
        (r"/_api/search/query.*startrow=0", fx("search_1.json")),
        (r"/_api/search/query.*startrow=2", fx("search_2.json")),
    ]


def page(tree, suffix):
    matches = [p for p in tree.pages if p.url.lower().endswith(suffix.lower())]
    assert len(matches) == 1, [p.url for p in tree.pages]
    return matches[0]


# -- the whole walk -------------------------------------------------------


def test_full_site_pages_webs_documents_and_sources():
    session = FakeSession(full_site_routes())
    tree, _t = run(session, search_page_size=2)

    assert tree.status == spt.STATUS_OK, tree.errors
    assert tree.web.title == "Portale" and tree.web.language == 1040
    assert [w.server_relative_url for w in tree.webs] == [
        "/sites/Portal", "/sites/Portal/Rischi"]

    urls = spt.seed_urls(tree)
    # Home pages first, the site's before the subsite's.
    assert urls[:2] == [f"{SITE}/SitePages/Home.aspx",
                        f"{SITE}/Rischi/SitePages/Home.aspx"]
    assert len(urls) == len(set(u.casefold() for u in urls))
    assert f"{SITE}/SitePages/Notizia-Ottobre.aspx" in urls  # page 2 of items
    assert f"{SITE}/SitePages/Archivio/Vecchia.aspx" in urls  # inside a folder
    assert len(urls) == 7

    news = page(tree, "Notizia-Ottobre.aspx")
    assert news.promoted_state == 2 and news.source == spt.SOURCE_SITEPAGES
    only_search = page(tree, "Solo%20Ricerca.aspx")
    assert only_search.source == spt.SOURCE_SEARCH
    assert only_search.modified == "2026-07-01T00:00:00Z"
    sub_search = page(tree, "Rischi/SitePages/Mappa.aspx")
    assert sub_search.web == f"{SITE}/Rischi"

    # The documents are inventoried, not audited.
    assert [d.url for d in tree.documents] == [
        f"{SITE}/Shared%20Documents/Regolamento.pdf"]


def test_dedup_is_case_insensitive_and_keeps_the_fileref_spelling():
    tree, _t = run(FakeSession(full_site_routes()), search_page_size=2)
    about = page(tree, "chi-siamo.aspx")
    assert about.url == f"{SITE}/SitePages/Chi-Siamo.aspx"
    assert about.source == spt.SOURCE_SITEPAGES
    assert set(about.sources) == {spt.SOURCE_SITEPAGES, spt.SOURCE_NAVIGATION,
                                  spt.SOURCE_SEARCH}
    # The bare web address in the navigation is the home page, not a new one.
    home = page(tree, "/sites/Portal/SitePages/Home.aspx")
    assert spt.SOURCE_NAVIGATION in home.sources


def test_out_of_scope_and_non_pages_are_counted_with_a_reason():
    tree, _t = run(FakeSession(full_site_routes()), search_page_size=2)
    counts = tree.skipped_counts()
    assert counts[spt.SKIP_OTHER_SITE] == 2      # /sites/Altro web + nav link
    assert counts[spt.SKIP_SYSTEM] == 1          # /_layouts/15/viewlsts.aspx
    assert counts[spt.SKIP_LIST_FORM] == 1       # Forms/AllItems.aspx
    assert counts[spt.SKIP_LIST_VIEW] == 1       # /Lists/Annunci
    assert counts[spt.SKIP_SHARING_LINK] == 1    # /:w:/r/...
    assert counts[spt.SKIP_OTHER_HOST] == 1      # www.example.org
    assert counts[spt.SKIP_NOT_HTTP] == 1        # mailto:
    assert counts[spt.SKIP_NO_LINK] == 1         # navigation header
    assert counts[spt.SKIP_FOLDER] == 1          # FSObjType 1
    assert not any("/sites/Altro" in p.url for p in tree.pages)
    # Skipped URLs carry no query string (sharing-link ids, tokens).
    assert all("?" not in s.url for s in tree.skipped)


def test_scope_is_segment_aware():
    # `/sites/Portal2` shares a prefix with `/sites/Portal` and is another site.
    routes = [
        (r"/_api/web\?\$select", fx("web.json")),
        (r"/_api/web/webs", EMPTY),
        (r"/_api/web/rootfolder", {"WelcomePage": ""}),
        (r"GetList\('/sites/Portal/SitePages'\)/items", {"value": [
            {"FileRef": "/sites/Portal/SitePages/A.aspx", "FSObjType": 0}]}),
        (r"/_api/web/lists\?", EMPTY),
        (r"navigation/QuickLaunch", {"value": [
            {"Title": "x", "Url": "/sites/Portal2/SitePages/B.aspx"},
            {"Title": "y", "Url": "/SITES/PORTAL/sitepages/c.aspx"}]}),
        (r"/_api/web/navigation/", EMPTY),
    ]
    tree, _t = run(FakeSession(routes), use_search=False)
    assert spt.seed_urls(tree) == [f"{SITE}/SitePages/A.aspx",
                                   f"{SITE}/sitepages/c.aspx"]
    assert tree.skipped_counts() == {spt.SKIP_OTHER_SITE: 1}


# -- page libraries -------------------------------------------------------


def test_items_paging_follows_the_next_link():
    session = FakeSession(full_site_routes())
    run(session, use_navigation=False, use_search=False)
    item_calls = [u for u in session.urls()
                  if "GetList('/sites/Portal/SitePages')/items" in u]
    assert len(item_calls) == 2
    assert "$top=500" in item_calls[0]
    assert "$skiptoken" in item_calls[1]


def test_library_is_never_looked_up_by_its_localized_title():
    session = FakeSession(full_site_routes())
    run(session)
    assert not any("getbytitle" in u.lower() for u in session.urls())


def test_page_library_at_a_localized_address_is_found_by_template():
    # No /SitePages: a publishing library at /Pagine (template 850), whose
    # items have no PromotedState column - the first select is refused.
    routes = [
        (r"/_api/web\?\$select", fx("web.json")),
        (r"/_api/web/webs", EMPTY),
        (r"/_api/web/rootfolder", {"WelcomePage": "Pagine/Default.aspx"}),
        (r"GetList\('/sites/Portal/SitePages'\)", not_found()),
        (r"GetList\('/sites/Portal/Pagine'\)/items\?\$select=.*PromotedState",
         FakeResponse(400, {"odata.error": {"message": {
             "value": "Column 'PromotedState' does not exist."}}})),
        (r"GetList\('/sites/Portal/Pagine'\)/items", {"value": [
            {"FileRef": "/sites/Portal/Pagine/Default.aspx", "Title": "Home",
             "FSObjType": 0},
            {"FileRef": "/sites/Portal/Pagine/Contatti.aspx",
             "Title": "Contatti", "FSObjType": 0}]}),
        (r"/_api/web/lists\?.*BaseTemplate eq 119 or BaseTemplate eq 850",
         {"value": [{"Title": "Pagine", "BaseTemplate": 850, "RootFolder": {
             "ServerRelativeUrl": "/sites/Portal/Pagine"}}]}),
        (r"/_api/web/navigation/", EMPTY),
    ]
    tree, _t = run(FakeSession(routes), use_search=False)
    assert tree.status == spt.STATUS_OK, tree.errors
    assert spt.seed_urls(tree) == [f"{SITE}/Pagine/Default.aspx",
                                   f"{SITE}/Pagine/Contatti.aspx"]
    # A missing /SitePages is not an error once another library answered.
    assert tree.errors == []


# -- subsites ------------------------------------------------------------


def test_subsite_cycle_is_not_followed_twice():
    session = FakeSession(full_site_routes())
    tree, _t = run(session, use_navigation=False, use_search=False)
    assert len(tree.webs) == 2
    webs_calls = [u for u in session.urls() if "/_api/web/webs" in u]
    assert len(webs_calls) == 2  # root and Rischi, never the root again


def test_web_count_and_depth_limits_truncate_visibly():
    tree, _t = run(FakeSession(full_site_routes()), max_webs=1,
                   use_navigation=False, use_search=False)
    assert [w.server_relative_url for w in tree.webs] == ["/sites/Portal"]
    assert tree.truncated and tree.status == spt.STATUS_PARTIAL
    assert tree.skipped_counts()[spt.SKIP_WEB_LIMIT] == 1

    session = FakeSession(full_site_routes())
    tree, _t = run(session, max_web_depth=0, use_navigation=False,
                   use_search=False)
    assert len(tree.webs) == 1
    assert not any("/_api/web/webs" in u for u in session.urls())


def test_starting_from_a_page_url_reads_its_web():
    session = FakeSession(full_site_routes())
    tree, _t = run(session, site=f"{SITE}/SitePages/Home.aspx",
                   use_navigation=False, use_search=False)
    assert session.urls()[0].startswith(f"{SITE}/_api/web?$select=")
    assert tree.web.server_relative_url == "/sites/Portal"


# -- search ---------------------------------------------------------------


def test_search_fills_in_when_libraries_cannot_be_read():
    routes = [
        (r"/_api/web\?\$select", fx("web.json")),
        (r"/_api/web/webs", EMPTY),
        (r"/_api/web/rootfolder", not_found()),
        (r"GetList", not_found()),
        (r"/_api/web/lists\?", FakeResponse(403, {"odata.error": {
            "message": {"value": "Access denied."}}})),
        (r"/_api/web/navigation/", EMPTY),
        (r"/_api/search/query.*startrow=0", fx("search_1.json")),
        (r"/_api/search/query.*startrow=2", fx("search_2.json")),
    ]
    session = FakeSession(routes)
    tree, _t = run(session, search_page_size=2)
    assert {p.source for p in tree.pages} == {spt.SOURCE_SEARCH}
    assert len(tree.pages) == 3  # two pages of results
    assert tree.status == spt.STATUS_PARTIAL  # the library errors are kept
    assert any(e.source == spt.SOURCE_SITEPAGES for e in tree.errors)
    query = next(u for u in session.urls() if "/_api/search/query" in u)
    assert f"querytext='path:\"{SITE}\" " in query
    assert "contentclass:STS_ListItem_WebPageLibrary'" in query
    assert "trimduplicates=false" in query and "rowlimit=2" in query


def test_search_verbose_shape_is_read_too():
    body = {"d": {"query": {"PrimaryQueryResult": {"RelevantResults": {
        "TotalRows": 1, "Table": {"Rows": {"results": [{"Cells": {"results": [
            {"Key": "Path", "Value": f"{SITE}/SitePages/V.aspx"}]}}]}}}}}}}
    rows, total = spt._search_rows(body)
    assert rows == [{"Path": f"{SITE}/SitePages/V.aspx"}] and total == 1


# -- throttling -----------------------------------------------------------


def minimal_routes(web_response):
    return [
        (r"/_api/web\?\$select", web_response),
        (r"/_api/web/webs", EMPTY),
        (r"/_api/web/rootfolder", {"WelcomePage": ""}),
        (r"GetList", EMPTY),
        (r"/_api/web/lists\?", EMPTY),
        (r"/_api/web/navigation/", EMPTY),
        (r"/_api/search/query", {}),
    ]


def test_429_waits_for_retry_after_then_succeeds():
    session = FakeSession(minimal_routes([
        FakeResponse(429, headers={"Retry-After": "7"}),
        fx("web.json")]))
    tree, t = run(session)
    assert t.slept == [7.0]
    assert tree.web is not None and tree.status == spt.STATUS_EMPTY


def test_503_backs_off_exponentially_up_to_max_wait():
    session = FakeSession(minimal_routes([
        FakeResponse(503), FakeResponse(503), FakeResponse(503),
        FakeResponse(503), fx("web.json")]))
    tree, t = run(session, max_wait=6, backoff_base=2)
    assert t.slept == [2, 4, 6, 6]
    assert tree.web is not None


def test_retry_after_beyond_max_wait_is_an_error_not_an_early_retry():
    session = FakeSession(minimal_routes([
        FakeResponse(429, headers={"Retry-After": "300"}), fx("web.json")]))
    tree, t = run(session, max_wait=120)
    assert t.slept == []
    assert len(session.calls) == 1
    assert tree.status == spt.STATUS_ERROR
    assert "300s" in tree.errors[0].message
    assert tree.errors[0].status == 429


def test_the_whole_walk_has_a_time_ceiling():
    session = FakeSession(minimal_routes([
        FakeResponse(503), FakeResponse(503), fx("web.json")]))
    tree, t = run(session, max_duration=5, backoff_base=2)
    # 2s of backoff fits, the next 4s does not: stop instead of sleeping.
    assert t.slept == [2]
    assert tree.truncated
    assert any(e.message == "time budget exhausted" for e in tree.errors)


def test_retry_after_as_http_date():
    t = FakeTime()
    when = spt.email.utils.formatdate(t.wall() + 30, usegmt=True)
    session = FakeSession(minimal_routes([
        FakeResponse(429, headers={"Retry-After": when}), fx("web.json")]))
    run(session, time=t)
    assert 29 <= t.slept[0] <= 31


def test_persistent_throttling_is_an_error_not_an_empty_site():
    session = FakeSession(minimal_routes(FakeResponse(429)))
    tree, t = run(session, max_retries=2)
    assert tree.status == spt.STATUS_ERROR
    assert tree.errors[0].status == 429
    assert len(t.slept) == 2


def test_pause_between_requests():
    session = FakeSession(minimal_routes(fx("web.json")))
    _tree, t = run(session, min_interval=0.5, use_search=False)
    # FakeTime does not advance between calls, so every gap is a full pause.
    assert t.slept and all(s == 0.5 for s in t.slept)
    assert len(t.slept) == len(session.calls) - 1


def test_request_budget_stops_the_walk_visibly():
    tree, _t = run(FakeSession(full_site_routes()), max_requests=3)
    assert tree.truncated and tree.requests_made == 3
    assert any(e.source == "budget" for e in tree.errors)
    assert tree.status in (spt.STATUS_PARTIAL, spt.STATUS_ERROR)


# -- sign-in -------------------------------------------------------------


@pytest.mark.parametrize("response, reason", [
    (FakeResponse(401), spt.AUTH_STATUS_401),
    (FakeResponse(403, headers={"X-Forms_Based_Auth_Required":
                                "https://contoso.sharepoint.com/_forms/x"}),
     spt.AUTH_FORMS_HEADER),
    (FakeResponse(302, headers={"Location":
                                "https://login.microsoftonline.com/common/oauth2"}),
     spt.AUTH_LOGIN_REDIRECT),
    (FakeResponse(302, headers={"Location": "/_forms/default.aspx?ReturnUrl=x"}),
     spt.AUTH_LOGIN_REDIRECT),
    (FakeResponse(200, text="<html><form action='https://login.microsoftonline.com/'>"),
     spt.AUTH_LOGIN_PAGE),
    # What SharePoint Online answers the crawler's user agent with: a plain
    # text 403 carrying the forms-auth header (shape recorded anonymously).
    (FakeResponse(403, headers={
        "Content-Type": "text/plain",
        "X-Forms_Based_Auth_Required":
            "https://contoso.sharepoint.com/_forms/default.aspx"
            "?ReturnUrl=/_layouts/15/error.aspx&Source=%2f",
        "X-MSDAVEXT_Error": "917656; Access denied."},
        text="403 FORBIDDEN"),
     spt.AUTH_FORMS_HEADER),
    # The browser's first hop towards Entra ID.
    (FakeResponse(302, headers={
        "Location": "/_layouts/15/Authenticate.aspx?Source=%2F"}),
     spt.AUTH_LOGIN_REDIRECT),
    (FakeResponse(302, headers={
        "Location": "https://contoso.b2clogin.com/x/oauth2/v2.0/authorize"}),
     spt.AUTH_LOGIN_REDIRECT),
])
def test_missing_or_expired_sign_in_is_its_own_result(response, reason):
    tree, _t = run(FakeSession(minimal_routes(response)))
    assert tree.auth_required and tree.auth_reason == reason
    assert tree.status == spt.STATUS_AUTH
    assert tree.pages == []


def test_bare_403_on_the_site_is_access_denied_not_sign_in():
    """Signed in, no permission: signing in again changes nothing, so it
    must not read as "sign in"."""
    response = FakeResponse(403, {"odata.error": {
        "code": "-2147024891, System.UnauthorizedAccessException",
        "message": {"value": "Access denied."}}})
    tree, _t = run(FakeSession(minimal_routes(response)))
    assert not tree.auth_required
    assert tree.access_denied and tree.status == spt.STATUS_ACCESS_DENIED
    assert tree.errors[0].source == "access"
    assert "sign-in" not in tree.errors[0].message


def test_session_expiring_mid_walk_keeps_what_was_read():
    routes = full_site_routes()
    # Both webs are listed first; the sign-in lapses on the subsite's pages.
    routes.insert(0, (r"/Rischi/_api/web/rootfolder", FakeResponse(401)))
    tree, _t = run(FakeSession(routes), use_search=False)
    assert tree.status == spt.STATUS_AUTH
    assert any(p.url.endswith("/sites/Portal/SitePages/Home.aspx")
               for p in tree.pages)


def test_empty_site_is_not_an_error():
    tree, _t = run(FakeSession(minimal_routes(fx("web.json"))))
    assert tree.status == spt.STATUS_EMPTY
    assert tree.errors == [] and not tree.auth_required


# -- what goes on the wire and into the result ------------------------------


def test_headers_are_decorated_and_no_cookie_is_added():
    session = FakeSession(minimal_routes(fx("web.json")))
    run(session, user_agent="ISV|Test|XAnalyze/1.0")
    for _url, headers in session.calls:
        assert headers["Accept"] == "application/json;odata=nometadata"
        assert headers["User-Agent"] == "ISV|Test|XAnalyze/1.0"
        assert "Cookie" not in headers and "Authorization" not in headers


def test_default_user_agent_has_the_microsoft_shape():
    assert re.fullmatch(r"ISV\|[^|]+\|XAnalyze/[\w.]+",
                        spt.default_user_agent())


def test_next_link_to_another_host_is_not_followed():
    routes = minimal_routes(fx("web.json"))
    routes[3] = (r"GetList", {"value": [], "odata.nextLink":
                              "https://evil.example/_api/steal"})
    session = FakeSession(routes)
    tree, _t = run(session, use_search=False)
    assert not any("evil.example" in u for u in session.urls())
    assert any("another host" in e.message for e in tree.errors)


def test_session_from_cookies_never_leaks_values_into_the_tree():
    secret = "synthetic-cookie-value-123"
    session = spt.session_from_cookies([{
        "name": "FedAuth", "value": secret,
        "domain": "contoso.sharepoint.com", "path": "/", "secure": True,
        "host_only": True}], SITE)
    assert [c.name for c in session.cookies] == ["FedAuth"]
    fake = FakeSession(minimal_routes(FakeResponse(401)))
    tree, _t = run(fake)
    assert secret not in repr(tree)


def test_documents_inventory_is_opt_in():
    routes = minimal_routes(fx("web.json"))
    routes.insert(3, (r"GetList\('/sites/Portal/Shared Documents'\)/items",
                      {"value": [
                          {"FileRef": "/sites/Portal/Shared Documents/a.docx",
                           "FSObjType": 0},
                          {"FileRef": "/sites/Portal/Shared Documents/Sub",
                           "FSObjType": 1}]}))
    routes.insert(3, (r"/_api/web/lists\?.*BaseTemplate eq 101", {"value": [
        {"RootFolder": {"ServerRelativeUrl":
                        "/sites/Portal/Shared Documents"}}]}))
    tree, _t = run(FakeSession(list(routes)), use_search=False)
    assert tree.documents == []
    tree, _t = run(FakeSession(list(routes)), use_search=False,
                   inventory_documents=True)
    assert [d.url for d in tree.documents] == [
        f"{SITE}/Shared%20Documents/a.docx"]
    assert tree.pages == []


# -- cross-check findings ---------------------------------------------------

HOST = "https://contoso.sharepoint.com"


def items(*refs):
    return {"value": [{"FileRef": r, "FileLeafRef": r.rsplit("/", 1)[-1],
                       "FSObjType": 0} for r in refs]}


def test_tenant_root_site_does_not_swallow_other_site_collections():
    session = FakeSession([
        (r"^https://contoso.sharepoint.com/_api/web\?\$select",
         {"Url": HOST, "ServerRelativeUrl": "/", "Title": "Root"}),
        (r"^https://contoso.sharepoint.com/_api/web/webs", {"value": [
            {"Url": f"{HOST}/hr", "ServerRelativeUrl": "/hr"},
            {"Url": f"{HOST}/sites/Other", "ServerRelativeUrl": "/sites/Other"}]}),
        (r"/_api/web/webs", EMPTY),
        (r"/_api/web/rootfolder", {"WelcomePage": "SitePages/Home.aspx"}),
        (r"GetList\('/SitePages'\)/items", items("/SitePages/Home.aspx")),
        (r"GetList\('/hr/SitePages'\)/items", items("/hr/SitePages/Home.aspx")),
        (r"/_api/web/lists\?", EMPTY),
        (r"^https://contoso.sharepoint.com/_api/web/navigation/QuickLaunch",
         {"value": [
             {"Title": "HR", "Url": "/sites/HR/SitePages/Home.aspx"},
             {"Title": "Team", "Url": "/teams/T/SitePages/Home.aspx"},
             {"Title": "Me", "Url": "/personal/someone/Documents/a.docx"}]}),
        (r"/_api/web/navigation/", EMPTY),
        (r"/_api/search/query", {"PrimaryQueryResult": {"RelevantResults": {
            "TotalRows": 1, "Table": {"Rows": [{"Cells": [
                {"Key": "Path",
                 "Value": f"{HOST}/sites/Finance/SitePages/Budget.aspx"}]}]}}}}),
    ])
    tree, _t = run(session, site=f"{HOST}/")
    assert spt.seed_urls(tree) == [f"{HOST}/SitePages/Home.aspx",
                                   f"{HOST}/hr/SitePages/Home.aspx"]
    assert [w.server_relative_url for w in tree.webs] == ["/", "/hr"]
    assert tree.skipped_counts()[spt.SKIP_OTHER_SITE] == 5
    query = next(u for u in session.urls() if "/_api/search/query" in u)
    for managed in ("sites", "teams", "personal"):
        assert f'-path:"{HOST}/{managed}"' in query


def test_page_templates_are_not_seeds():
    routes = minimal_routes(fx("web.json"))
    routes[3] = (r"GetList", items(
        "/sites/Portal/SitePages/Home.aspx",
        "/sites/Portal/SitePages/Templates/News template.aspx"))
    tree, _t = run(FakeSession(routes), use_search=False)
    assert spt.seed_urls(tree) == [f"{SITE}/SitePages/Home.aspx"]
    assert tree.skipped_counts() == {spt.SKIP_PAGE_TEMPLATE: 1}


def test_a_subsite_called_lists_or_forms_keeps_its_pages():
    routes = [
        (r"/sites/Portal/_api/web\?\$select", fx("web.json")),
        (r"/sites/Portal/(Lists|Forms)/_api/web/webs", EMPTY),
        (r"/sites/Portal/_api/web/webs", {"value": [
            {"Url": f"{SITE}/Lists", "ServerRelativeUrl": "/sites/Portal/Lists"},
            {"Url": f"{SITE}/Forms", "ServerRelativeUrl": "/sites/Portal/Forms"}]}),
        (r"/_api/web/rootfolder", {"WelcomePage": ""}),
        (r"GetList\('/sites/Portal/Lists/SitePages'\)",
         items("/sites/Portal/Lists/SitePages/A.aspx")),
        (r"GetList\('/sites/Portal/Forms/SitePages'\)",
         items("/sites/Portal/Forms/SitePages/B.aspx")),
        (r"GetList", EMPTY),
        (r"/_api/web/lists\?", EMPTY),
        (r"/sites/Portal/Lists/_api/web/navigation/QuickLaunch", {"value": [
            {"Title": "x",
             "Url": "/sites/Portal/Lists/Lists/Tasks/AllItems.aspx"}]}),
        (r"/_api/web/navigation/", EMPTY),
    ]
    tree, _t = run(FakeSession(routes), use_search=False)
    urls = spt.seed_urls(tree)
    assert f"{SITE}/Lists/SitePages/A.aspx" in urls
    assert f"{SITE}/Forms/SitePages/B.aspx" in urls
    # A real list inside that subsite is still a list.
    assert tree.skipped_counts().get(spt.SKIP_LIST_FORM) == 1
