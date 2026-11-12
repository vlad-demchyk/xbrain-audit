"""xFormat provider — calls billed to the user's xFormat subscription
instead of a personal Anthropic key.

This was written against a guessed `/api/v1/*` contract before the backend
was settled. It is now written against the real one, read from the backend
source (`xformat-backend/api/src/`):

    POST {base}/api/auth/login      {"email", "password"}
      -> {"user": {"id", "email"},
          "accessToken", "accessTokenExpiresAt"}
         and a refresh token in the httpOnly cookie `xf_refresh_token`

    POST {base}/api/auth/refresh    {"refreshToken"}  (optional — see below)
      -> the same shape

    POST {base}/api/auth/logout
      -> revokes the session server-side, not just locally

    GET  {base}/api/me
      -> {"profile": {"email", "plan", ...},
          "usage": {"tokensAllocated", "tokensUsed", ...} | null,
          "stats": {...}}

    POST {base}/api/ai/{feature}    {"messages": [{"role", "content"}]}
      -> {"message": {"role", "content"}, "usage", "execution": {"model"}}

Three things about this backend shape are worth knowing, because each one
caused a bug in the first version:

**The refresh token lives in a cookie, and only in a cookie.** The web app
never sees it, and - verified live on 2026-08-19 - neither `login` nor
`refresh` puts it in the response body: the only carrier is `Set-Cookie`.
A desktop client has no browser cookie jar that survives a restart, so the
cookie is read out of each response and stored like any other secret, then
replayed two ways on refresh: in the session's cookie jar *and* in the
request body. The backend accepts either (the body fallback exists for the
native apps for exactly this reason), and sending both means one
implementation covers a cookie that was rotated and a cookie that was never
received.

**Refresh rotates, and the old token is spent immediately.** Replaying one
answers 401 `Invalid Refresh Token: Already Used`, so the stored copy must
be replaced after every call. It must be read from the response that issued
it rather than from the jar: the jar can hold two cookies of this name at
once - the primed one on the API host at path `/`, and the server's on
`.xformat.net` at path `/api/auth` - and asking such a jar for one value
raises. That is what kept a spent token stored in the first version.

**The access token has two clocks.** Supabase issues it for about an hour,
but this API only accepts it for the first 15 minutes
(`accessTokenExpiresAt` in the response says when it stops being accepted).
Trusting the JWT's own expiry would mean 45 minutes of 401s per session, so
the value from the response body is what is stored — as an absolute
millisecond timestamp, not a duration.

`XFormatEndpoints` still exists and is still overridable from Settings, so
a backend change can be corrected without shipping a new build; the
defaults are simply real now rather than hypothetical.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .base import (
    REWRITE_SYSTEM_PROMPT, AuthStatus, LLMAppNotPermitted, LLMProvider,
    LLMProviderFactory, LLMAuthError, LLMUnavailable, prompt_language,
)
from . import credentials

#: The production API. Mirrors `BUILTIN_API_URL` in the frontend's
#: `packages/core/src/saasAuth/backendUrl.ts` — the app domain
#: (app.xformat.net) serves the web client, not the API.
DEFAULT_BASE_URL = "https://api.xformat.net"

#: Name of the backend's refresh cookie (`api/src/lib/refreshCookie.ts`).
REFRESH_COOKIE = "xf_refresh_token"

#: How this client identifies itself to the backend
#: (`api/src/lib/clientApps.ts`). The backend uses it for two things: to decide
#: what "Auto" means for this application, and to attribute the cost in the
#: ledger. It is *not* authentication - what this app may do on someone's
#: behalf is a row in `user_app_grants` that the user can revoke, which is why
#: `sign_in` can succeed and an AI call can still come back asking for consent.
#: The client app's id in the xFormat backend (`client_apps.slug`). It was
#: `xanalyze` before the rename to XBrain Audit; the backend keeps that as an
#: alias forever (xformat-backend `appSlugAliases.ts`), so builds that still
#: send it keep working.
CLIENT_APP_SLUG = "xbrain-audit"
CLIENT_APP_HEADER = "X-Client-App"

ACCESS_TOKEN_KEY = "xformat_access_token"
REFRESH_TOKEN_KEY = "xformat_refresh_token"
ACCOUNT_EMAIL_KEY = "xformat_account_email"

#: Backend AI features usable from here (`api/src/lib/featureModelMap.ts`).
#: `cleanup` is the grammar/structure rewrite of text the user already has —
#: exactly this tool's job, and the cheapest tier on every plan, so a bulk
#: rewrite of a hundred flagged passages doesn't eat someone's month.
FEATURE_REWRITE = "cleanup"
#: Used by the xFormat-billed judge detector: an analysis task
#: rather than a rewrite.
FEATURE_ANALYZE = "document_analysis"


@dataclass
class XFormatEndpoints:
    """Everything backend-shape-specific, in one editable place.

    Overridable as JSON from Settings → Advanced, so a contract change can
    be corrected in the field. Dotted paths are supported in the response
    field names (`profile.email`).
    """
    login_path: str = "/api/auth/login"
    refresh_path: str = "/api/auth/refresh"
    logout_path: str = "/api/auth/logout"
    me_path: str = "/api/me"
    apps_path: str = "/api/me/apps"
    app_grant_path: str = "/api/me/apps/{app}/grant"
    ai_path: str = "/api/ai/{feature}"
    rewrite_feature: str = FEATURE_REWRITE
    analyze_feature: str = FEATURE_ANALYZE

    # request field names
    login_email_field: str = "email"
    login_password_field: str = "password"
    refresh_token_field: str = "refreshToken"

    # response field names (dotted paths supported)
    access_token_field: str = "accessToken"
    access_expires_at_field: str = "accessTokenExpiresAt"
    refresh_token_response_field: str = "refreshToken"
    message_content_field: str = "message.content"
    me_email_field: str = "profile.email"
    me_plan_field: str = "profile.plan"
    me_tokens_allocated_field: str = "usage.tokensAllocated"
    me_tokens_used_field: str = "usage.tokensUsed"

    extra_headers: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict | None) -> "XFormatEndpoints":
        if not data:
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


def _dig(payload, dotted: str):
    """Read 'a.b.c' out of nested dicts; returns None if any hop is missing
    or holds null (the backend sends `usage: null` for a free account)."""
    node = payload
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


class XFormatProvider(LLMProvider):
    name = "xformat"
    display_name = "xFormat subscription (app.xformat.net account)"
    uses_account = True

    def __init__(self, base_url: str = DEFAULT_BASE_URL, endpoints: dict | None = None,
                 timeout: float = 60.0, verify_tls: bool = True,
                 client_app: str = CLIENT_APP_SLUG, **config):
        super().__init__(**config)
        self.client_app = client_app or CLIENT_APP_SLUG
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.endpoints = XFormatEndpoints.from_dict(endpoints)
        self.timeout = timeout
        self.verify_tls = verify_tls
        self._session = None
        #: The refresh cookie from the most recent response, if that response
        #: set one. Read from the response rather than from the jar because a
        #: jar can hold two cookies of this name at once - the one primed from
        #: the keychain and the one the server just issued - and the one that
        #: matters is always the newer.
        self._issued_refresh_token: str | None = None
        self._access_token: str | None = credentials.load_secret(ACCESS_TOKEN_KEY)
        self._refresh_token: str | None = credentials.load_secret(REFRESH_TOKEN_KEY)
        # Unknown until the next login or refresh: a token restored from the
        # keychain carries no expiry with it. Zero means "don't pre-emptively
        # refresh", and the 401-retry path covers an expired one.
        self._access_expires_at: float = 0.0

    # ------------------------------------------------------------- plumbing

    def _get_session(self):
        if self._session is not None:
            return self._session
        try:
            import requests
        except ImportError as exc:
            raise LLMUnavailable("The 'requests' package is not installed.") from exc
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "AIContentScanner/0.1",
            "Accept": "application/json",
            "Content-Type": "application/json",
            CLIENT_APP_HEADER: self.client_app,
            **self.endpoints.extra_headers,
        })
        if self._refresh_token:
            self._prime_refresh_cookie()
        return self._session

    def _prime_refresh_cookie(self) -> None:
        """Put the stored refresh token back in the cookie jar, so a refresh
        works the same way it does in a browser.

        Every older copy is cleared first. The backend sets this cookie on
        `.xformat.net` with path `/api/auth`, and a copy primed here lands on
        the API host with path `/`; both match a refresh request, so leaving
        the old one in place means the jar carries two cookies of the same
        name and reading it back becomes ambiguous.
        """
        from urllib.parse import urlparse
        domain = urlparse(self.base_url).hostname or ""
        self._clear_refresh_cookies()
        try:
            self._session.cookies.set(REFRESH_COOKIE, self._refresh_token, domain=domain)
        except Exception:  # noqa: BLE001 - a cookie jar that refuses is not fatal;
            pass          # the body fallback below still carries the token.

    def _clear_refresh_cookies(self) -> None:
        """Drop every copy of the refresh cookie, whatever domain or path it
        was set on."""
        session = self._session
        if session is None:
            return
        stale = [(c.domain, c.path) for c in session.cookies if c.name == REFRESH_COOKIE]
        for domain, path in stale:
            try:
                session.cookies.clear(domain, path, REFRESH_COOKIE)
            except KeyError:
                pass

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request(self, method: str, path: str, payload: dict | None = None,
                 authed: bool = False, auth_error_message: str | None = None) -> dict:
        session = self._get_session()
        headers = {}
        if authed:
            headers["Authorization"] = f"Bearer {self._access_token}"
        try:
            resp = session.request(
                method, self._url(path), json=payload, headers=headers,
                timeout=self.timeout, verify=self.verify_tls,
            )
        except Exception as exc:  # noqa: BLE001 - requests raises a family of errors
            raise LLMUnavailable(f"Could not reach {self.base_url}: {exc}") from exc
        # Read before the response is turned into an exception: a 401 from
        # refresh clears the cookie, and that is a fact worth recording too.
        self._issued_refresh_token = resp.cookies.get(REFRESH_COOKIE) or None
        return self._handle_response(resp, auth_error_message)

    def _post(self, path: str, payload: dict, authed: bool,
              auth_error_message: str | None = None) -> dict:
        return self._request("POST", path, payload, authed, auth_error_message)

    def _get(self, path: str) -> dict:
        return self._request("GET", path, None, authed=True)

    @staticmethod
    def _handle_response(resp, auth_error_message: str | None = None) -> dict:
        body: dict = {}
        try:
            parsed = resp.json()
            if isinstance(parsed, dict):
                body = parsed
        except ValueError:
            body = {}
        code = body.get("error") if isinstance(body.get("error"), str) else None
        # The backend writes a human sentence next to the code. Preferring it
        # over a generic line means a limit this client has never heard of
        # still arrives at the user as an instruction rather than as a number.
        detail = body.get("message") if isinstance(body.get("message"), str) else None

        if code in _APP_ERRORS:
            # Raised for any status: the message is the actionable part, and a
            # sign-in prompt here would send the user round a loop that cannot
            # fix it.
            raise LLMAppNotPermitted(_APP_ERRORS[code])
        if resp.status_code in (401, 403):
            raise LLMAuthError(
                _AUTH_ERRORS.get(code)
                or auth_error_message
                or detail
                or "xFormat rejected the session (signed out or expired)."
            )
        if resp.status_code == 402:
            raise LLMUnavailable(
                _QUOTA_ERRORS.get(code)
                or detail
                or "The xFormat subscription is inactive or out of budget."
            )
        if resp.status_code == 429:
            # Not every 429 is "wait a moment". A weekly allowance that is used
            # up resets next week, and telling someone to try again shortly
            # sends them back into the same wall every few minutes.
            raise LLMUnavailable(
                _RATE_ERRORS.get(code)
                or detail
                or "xFormat rate limit reached — try again shortly."
            )
        if resp.status_code == 503 and code:
            raise LLMUnavailable(f"xFormat is temporarily unable to serve this ({code}).")
        if resp.status_code >= 400:
            raise LLMUnavailable(
                f"xFormat error {resp.status_code}: "
                f"{detail or code or (resp.text or '')[:300]}")
        if not body:
            raise LLMUnavailable(
                f"xFormat returned a non-JSON response ({resp.status_code}). "
                "Check the base URL and the endpoint paths in Settings."
            )
        return body

    # ----------------------------------------------------------------- auth

    def sign_in(self, email: str, password: str) -> AuthStatus:
        """Exchange credentials for tokens. The password is not persisted."""
        ep = self.endpoints
        data = self._post(
            ep.login_path,
            {ep.login_email_field: email, ep.login_password_field: password},
            authed=False,
            auth_error_message="xFormat rejected these credentials — check the email and password.",
        )
        access = _dig(data, ep.access_token_field)
        if not access:
            raise LLMUnavailable(
                f"Sign-in succeeded but no '{ep.access_token_field}' was in the "
                "response. Adjust the field mapping in Settings to match the API."
            )
        self._store_tokens(
            access,
            # The web flow keeps the refresh token in the cookie only; read it
            # out of the jar so the desktop session survives a restart.
            _dig(data, ep.refresh_token_response_field) or self._cookie_refresh_token(),
            _dig(data, ep.access_expires_at_field),
        )
        credentials.save_secret(ACCOUNT_EMAIL_KEY, email)
        return self.auth_status()

    def _cookie_refresh_token(self) -> str | None:
        """The refresh token the backend last issued.

        The response's own cookies come first. Reading the session jar instead
        is what the first version did, and it silently kept a spent token:
        `refresh` answers with no `refreshToken` in the body and a fresh cookie
        on `.xformat.net` path `/api/auth`, while the copy primed from the
        keychain sits on the API host at path `/`. Two cookies of one name make
        `jar.get()` raise, the exception was swallowed, and the stale token
        stayed stored - so the next run started with a token the backend had
        already marked used, and the session died on restart rather than at
        sign-out. Confirmed against the live API on 2026-08-19: replaying a
        spent token answers 401 `Invalid Refresh Token: Already Used`.
        """
        if self._issued_refresh_token:
            return self._issued_refresh_token
        session = self._session
        if session is None:
            return None
        values = [c.value for c in session.cookies
                  if c.name == REFRESH_COOKIE and c.value]
        return values[-1] if values else None

    def sign_out(self) -> None:
        """Revoke server-side first, then forget locally.

        Order matters: clearing the tokens first would leave a session alive
        on the backend that this client can no longer end.
        """
        if self._access_token:
            try:
                self._post(self.endpoints.logout_path, {}, authed=True)
            except (LLMUnavailable, LLMAuthError):
                pass  # already invalid, or offline — local sign-out proceeds
        self._access_token = None
        self._refresh_token = None
        self._issued_refresh_token = None
        self._access_expires_at = 0.0
        if self._session is not None:
            self._session.cookies.clear()
        for key in (ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY, ACCOUNT_EMAIL_KEY):
            credentials.delete_secret(key)

    def _forget_refresh_token(self) -> None:
        self._refresh_token = None
        self._issued_refresh_token = None
        self._clear_refresh_cookies()
        credentials.delete_secret(REFRESH_TOKEN_KEY)

    def _store_tokens(self, access: str, refresh: str | None, expires_at) -> None:
        self._access_token = access
        credentials.save_secret(ACCESS_TOKEN_KEY, access)
        if refresh:
            # Always overwrite: the backend rotates the refresh token on every
            # refresh and invalidates the previous one, so keeping the old
            # value would break the *next* refresh, not this one.
            self._refresh_token = refresh
            credentials.save_secret(REFRESH_TOKEN_KEY, refresh)
            self._prime_refresh_cookie()
        try:
            # Milliseconds since the epoch, per `accessTokenExpiresAt`. Renew a
            # minute early so a call can't start on a token that expires while
            # it is in flight.
            self._access_expires_at = (float(expires_at) / 1000.0) - 60 if expires_at else 0.0
        except (TypeError, ValueError):
            self._access_expires_at = 0.0

    def _refresh_access_token(self) -> bool:
        ep = self.endpoints
        if not self._refresh_token and not self._cookie_refresh_token():
            return False
        payload = {}
        if self._refresh_token:
            # Sent in the body as well as the cookie: the backend accepts
            # either, and the native path exists precisely because a
            # non-browser client's cookie jar can't be relied on.
            payload[ep.refresh_token_field] = self._refresh_token
        try:
            data = self._post(ep.refresh_path, payload, authed=False)
        except LLMAuthError:
            # The backend refuses this token and will refuse it again: refresh
            # tokens are single-use here. Forgetting it is what makes the next
            # status check say "signed out" instead of retrying a dead token
            # for the life of the install.
            self._forget_refresh_token()
            return False
        except LLMUnavailable:
            # Offline or a backend fault says nothing about the token, so it
            # is kept.
            return False
        access = _dig(data, ep.access_token_field)
        if not access:
            return False
        self._store_tokens(
            access,
            _dig(data, ep.refresh_token_response_field) or self._cookie_refresh_token(),
            _dig(data, ep.access_expires_at_field),
        )
        return True

    def _ensure_token(self) -> None:
        if not self._access_token:
            raise LLMAuthError(
                "Not signed in to xFormat — sign in from Settings, or switch "
                "the provider to your own Anthropic key."
            )
        if self._access_expires_at and time.time() >= self._access_expires_at:
            self._refresh_access_token()

    def _authed_call(self, fn):
        """Run an authenticated call, refreshing once on a 401."""
        self._ensure_token()
        try:
            return fn()
        except LLMAuthError:
            if self._refresh_access_token():
                return fn()
            raise

    def auth_status(self, *, read_only: bool = False) -> AuthStatus:
        if not self._access_token:
            return AuthStatus(signed_in=False, detail="not signed in")
        ep = self.endpoints
        try:
            # GUI probes may finish after signing out or changing accounts.
            # They must never refresh/save credentials from that old snapshot.
            data = self._get(ep.me_path) if read_only else self._authed_call(lambda: self._get(ep.me_path))
        except LLMAuthError as exc:
            if read_only and self._refresh_token:
                email = credentials.load_secret(ACCOUNT_EMAIL_KEY) or ""
                # A locally held session may refresh on the user's next AI
                # request; the passive probe neither renews nor erases it.
                return AuthStatus(signed_in=True, detail=email)
            return AuthStatus(signed_in=False, detail=str(exc))
        except LLMUnavailable as exc:
            # Signed in as far as we know, but the check itself failed —
            # report that honestly rather than claiming either state.
            email = credentials.load_secret(ACCOUNT_EMAIL_KEY) or ""
            return AuthStatus(signed_in=True, detail=f"{email} (status check failed: {exc})")

        email = _dig(data, ep.me_email_field) or credentials.load_secret(ACCOUNT_EMAIL_KEY) or ""
        plan = _dig(data, ep.me_plan_field)
        detail = " · ".join(str(x) for x in (email, plan) if x)
        return AuthStatus(
            signed_in=True,
            detail=detail or "signed in",
            quota_remaining=_remaining_tokens(data, ep),
        )

    # ------------------------------------------------------- app consent

    def list_apps(self) -> list:
        """Which applications exist on this backend, and which this account
        has let in. Cheap and billing-free, like `/api/me`."""
        data = self._authed_call(lambda: self._get(self.endpoints.apps_path))
        apps = data.get("apps")
        return apps if isinstance(apps, list) else []

    def app_state(self, slug: str | None = None) -> dict | None:
        """This app's own row from `list_apps`, or None if the backend does
        not know it (an older deployment, or a different one)."""
        target = slug or self.client_app
        for app in self.list_apps():
            if isinstance(app, dict) and app.get("slug") == target:
                return app
        return None

    def grant_app(self, slug: str | None = None) -> dict:
        """Let this application use the signed-in account.

        Consent is given by the account holder, so it is a normal authenticated
        call rather than anything privileged: the token already proves who is
        agreeing.
        """
        path = self.endpoints.app_grant_path.format(app=slug or self.client_app)
        return self._authed_call(lambda: self._post(path, {}, authed=True))

    def revoke_app(self, slug: str | None = None) -> dict:
        """Take that consent back. The backend keeps the row and stamps it, so
        "granted once and revoked" stays distinguishable from "never granted"."""
        path = self.endpoints.app_grant_path.format(app=slug or self.client_app)
        return self._authed_call(
            lambda: self._request("DELETE", path, None, authed=True))

    # -------------------------------------------------------------- calls

    def _chat(self, feature: str, system: str, user_text: str) -> str:
        ep = self.endpoints
        path = ep.ai_path.format(feature=feature)
        payload = {
            "messages": [
                # The backend takes a plain message list; a system prompt is
                # a `system`-role entry in it rather than a separate field.
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ]
        }
        data = self._authed_call(lambda: self._post(path, payload, authed=True))
        content = _dig(data, ep.message_content_field)
        if not isinstance(content, str) or not content.strip():
            raise LLMUnavailable(
                f"xFormat response had no usable '{ep.message_content_field}' field. "
                "Adjust the field mapping in Settings to match the API."
            )
        return content.strip()

    def rewrite(self, text: str, language: str | None = None) -> str:
        language = prompt_language(language)
        prompt = f"{text}\n\n(language: {language})" if language else text
        return self._chat(self.endpoints.rewrite_feature, REWRITE_SYSTEM_PROMPT, prompt)

    def analyze(self, system: str, user_text: str) -> str:
        """Used by the xFormat-billed judge detector — same session, same
        subscription, different backend feature."""
        return self._chat(self.endpoints.analyze_feature, system, user_text)


def _remaining_tokens(data: dict, ep: XFormatEndpoints) -> int | None:
    """Budget left this period, or None for a plan that doesn't meter it.

    The backend reports an allocation and a used figure rather than a
    remainder, and sends `usage: null` for accounts without a metered plan —
    so "no number" is a normal answer here, not a failure.
    """
    allocated = _dig(data, ep.me_tokens_allocated_field)
    used = _dig(data, ep.me_tokens_used_field)
    if allocated is None or used is None:
        return None
    try:
        return max(0, int(allocated) - int(used))
    except (TypeError, ValueError):
        return None


# Backend error codes worth translating into an instruction rather than
# showing raw. Anything not listed falls through to the generic message.
#: 403 codes that are about the *application*, not the session. Kept apart from
#: `_AUTH_ERRORS` because signing in again fixes none of them: the user has to
#: allow the app, or an admin has to re-enable it.
_APP_ERRORS = {
    "client_app_grant_required": (
        "This xFormat account has not allowed XBrain Audit to use it yet. Run "
        "`cli.py ai grant`, or allow it in your xFormat account settings."
    ),
    "client_app_disabled": "XBrain Audit is currently disabled on the xFormat backend.",
    "unknown_client_app": (
        "The xFormat backend does not recognise this application. It may be "
        "running against a deployment where XBrain Audit is not registered."
    ),
}

_AUTH_ERRORS = {
    "account_suspended": "This xFormat account is suspended — contact support.",
    "account_deleted": "This xFormat account no longer exists.",
    "missing_refresh_token": "The xFormat session expired — sign in again from Settings.",
    "refresh_failed": "The xFormat session could not be renewed — sign in again from Settings.",
}
#: 429 codes. Confirmed live on 2026-08-19: a free account answers
#: `weekly_limit_exceeded` to `/api/ai/cleanup`, which is a plan limit wearing
#: the status code of a rate limit.
_RATE_ERRORS = {
    "weekly_limit_exceeded": (
        "This xFormat plan's weekly AI allowance is used up. It resets next "
        "week; a higher plan raises the limit. The offline engine keeps working."
    ),
    "daily_limit_exceeded": (
        "This xFormat plan's daily AI allowance is used up. It resets tomorrow; "
        "the offline engine keeps working."
    ),
}

_QUOTA_ERRORS = {
    "budget_exceeded": "The xFormat plan's budget for this period is used up.",
    "insufficient_credits": "Not enough xFormat credits left for this request.",
}


LLMProviderFactory.register(XFormatProvider.name, XFormatProvider)
