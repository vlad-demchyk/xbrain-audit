"""What the target implies about how to read it.

`project_profile` answers *what a directory is*. This module answers the
question that follows and that nothing asked before: **so what should this
run do differently?**

Until now the answer lived nowhere. The window drew a "Project profile"
card that named the stack and changed nothing; the terminal form offered the
same eleven controls for a URL, a folder and a single `.html` file, most of
which were dead for two of the three. A person had to know that
`--web-parts` needs a checkout, that `--depth` means nothing to a folder,
and that a Vite app scanned off disk is markup a bundler has not run yet.
That is knowledge the tool has and was making the person supply.

Two rules hold this honest, and they are the same two that hold
`project_profile` honest:

**Nothing is enabled silently.** Every suggestion carries the stack that
asked for it and the marker file that proved that stack, so "enabled, because
…" is a sentence a surface can print and a person can disagree with. A
suggestion is applied only to an option the person has not touched -
`apply` takes the set of options they set by hand and never overwrites one.

**A field is hidden only when it reaches nothing.** `fields_for` is derived
from what each option needs, not from a per-screen list: a crawl depth needs
pages to crawl, `--incremental` needs files on disk with mtimes. Hiding
anything else would be tidying, and tidying is how a control that mattered
became unreachable - which is the defect this whole module is a reaction to.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

#: A live address, crawled.
KIND_SITE = "site"
#: A directory on disk, read as files.
KIND_REPO = "repo"
#: One document, named directly.
KIND_FILE = "file"

KINDS = (KIND_SITE, KIND_REPO, KIND_FILE)


def target_kind(target: str, forced_url: bool = False) -> str:
    """Site, folder or single file - decided exactly as the CLI decides it.

    One function rather than three surfaces each re-deriving it: `cmd_audit`
    already reads `looks_like_url(target) or args.url` and then
    `_is_page_file(target)`, and a form that guessed differently from the
    command it is about to call would show fields for a run that never
    happens.
    """
    from cli_impl.auditpass import _is_page_file, looks_like_url

    text = (target or "").strip()
    if not text:
        return KIND_SITE
    if forced_url or looks_like_url(text):
        return KIND_SITE
    if _is_page_file(text):
        return KIND_FILE
    path = Path(text)
    if path.is_dir():
        return KIND_REPO
    if path.is_file():
        return KIND_FILE
    # Neither on disk nor host-shaped: the run will say so. `repo` is the
    # reading that shows the most fields, so nothing is hidden from a person
    # still typing a path.
    return KIND_REPO


#: Every run option a surface can offer, and what it needs to mean anything.
#:
#: `kinds` is the whole rule: an option is offered for a target of that kind
#: and hidden for the others. Nothing here is about screen space - a control
#: that is merely crowded stays.
_OPTION_KINDS = {
    # Crawling: needs an address and links to follow.
    "depth": (KIND_SITE,),
    "max_pages": (KIND_SITE,),
    "site_controls": (KIND_SITE,),
    "no_session": (KIND_SITE,),
    # Where the list of pages comes from: `""` follows links, `sharepoint`
    # asks the site for its own page tree (`sharepoint_tree.discover`).
    "page_tree": (KIND_SITE,),
    # A path the crawl stays inside, such as one SharePoint site collection
    # on a host that serves the whole tenant.
    "site_scope": (KIND_SITE,),
    # The checkout behind a served page. A folder run is already reading the
    # files and has nothing to pair against; a page - fetched or saved to
    # disk - has a repository somewhere that wrote it, and `analyze_page_file`
    # takes the parts read out of it exactly as the crawl branch does.
    "repo": (KIND_SITE, KIND_FILE),
    # Files on disk.
    "max_files": (KIND_REPO,),
    "ext": (KIND_REPO,),
    "exclude": (KIND_REPO,),
    "use_default_excludes": (KIND_REPO,),
    "no_default_excludes": (KIND_REPO,),
    "incremental": (KIND_REPO,),
    "devserver": (KIND_REPO,),
    "start_command": (KIND_REPO,),
    "dev_server_port": (KIND_REPO,),
    # What the documents in a folder are *for*. One named file settles it by
    # its own suffix and headers; a site is a site.
    "medium": (KIND_REPO,),
    # One deliverable out of a folder that holds several.
    "project": (KIND_REPO,),
    # Reads part manifests out of a checkout - see `audit/spfx.py`.
    "web_parts": (KIND_SITE, KIND_FILE),
    # Everything below reaches all three, and is listed so the table is the
    # single answer to "is this option meaningful here" rather than a
    # partial one that silently says no to anything unlisted.
    "scope": (KIND_SITE, KIND_REPO),
    "breakpoints": KINDS,
    "no_browser": KINDS,
    "render": KINDS,
    "within": KINDS,
    "category": KINDS,
    "confidence": KINDS,
    "unsettled": KINDS,
    # Only a web audit has a server whose headers can be left out; the table
    # still answers "is this option meaningful here" for every kind.
    "include_environment": (KIND_SITE,),
    "language": KINDS,
    "detector": KINDS,
    "model": KINDS,
    "effort": KINDS,
    "no_judgment_cache": KINDS,
    "ai": KINDS,
    "fix": KINDS,
    "agent": KINDS,
    "report": KINDS,
    "styled_report": KINDS,
    "json": KINDS,
    "check": KINDS,
}


def fields_for(kind: str) -> tuple:
    """Which options mean anything for a target of this kind, sorted."""
    return tuple(sorted(name for name, kinds in _OPTION_KINDS.items()
                        if kind in kinds))


def applies(option: str, kind: str) -> bool:
    """Does `option` reach anything for a target of this kind?

    An option nobody listed is *shown*, deliberately. A new flag that nobody
    remembered to add here must appear on every surface rather than vanish
    from all of them.
    """
    kinds = _OPTION_KINDS.get(option)
    return True if kinds is None else kind in kinds


@dataclass(frozen=True)
class Suggestion:
    """One parameter this target asks for, and who asked."""
    #: The argparse destination, so a surface can set it without a mapping.
    option: str
    value: object
    #: Translation key for the sentence that says why. Surfaces render it;
    #: this module holds no prose, the same way `report/` holds its own.
    reason: str
    #: The stack that asked, as `project_profile` names it. Empty when the
    #: target's own kind asked - a single file needs no stack to be one file.
    stack: str = ""
    #: The marker file that proved the stack. Empty for a kind-only
    #: suggestion, and never invented: it is copied from `Profile.evidence`.
    evidence: str = ""


@dataclass(frozen=True)
class Recipe:
    """A stack (or a kind) and the option it implies."""
    option: str
    #: The value, or a callable taking the target and returning it - for an
    #: option whose value is read off the address, such as a site's path.
    value: object
    reason: str
    stacks: tuple = ()
    kinds: tuple = KINDS
    #: Only when no checkout is paired with the site. A run that names a
    #: repository is about the parts that repository ships, not the site's
    #: every page.
    without_repo: bool = False


#: Every stack that ships a dev server whose output is the page, not its
#: source. Scanning these off disk reads templates a bundler has not run:
#: `<App />` is not a heading, and the rules that look for headings find
#: nothing to say about it.
_SERVED_STACKS = ("nextjs", "nuxt", "vite", "gatsby", "sveltekit", "astro",
                  "remix", "angular", "qwik", "ember", "docusaurus",
                  "eleventy", "hugo", "jekyll")

#: What each stack asks for. Deliberately short: a suggestion is a promise
#: that the run is better with it, and only the ones that were measured or
#: are structurally certain are here. A stack whose best settings nobody has
#: measured contributes nothing and its scan is exactly what it was.
RECIPES = (
    # SPFx: the deliverable is a web part, and the page it lands on belongs
    # to somebody else's SharePoint site. `--web-parts` reads the part
    # manifests out of the checkout and confines the audit to what those
    # parts actually render - which is why it needs both halves, the site
    # and the repository that ships into it, and why it is suggested only
    # once both are named.
    Recipe(option="web_parts", value=True, reason="why_web_parts",
           stacks=("spfx",), kinds=(KIND_SITE, KIND_FILE)),
    Recipe(option="devserver", value=True, reason="why_devserver",
           stacks=_SERVED_STACKS, kinds=(KIND_REPO,)),
    # One document has no second page to crawl to and no site to compare
    # against, so the only axis left is how wide the viewport is - and the
    # width that finds WCAG 1.4.10 overflow is not the default one.
    Recipe(option="breakpoints", value="all", reason="why_breakpoints_file",
           kinds=(KIND_FILE,)),
    # SharePoint: every modern page is assembled in the browser, so a plain
    # fetch reads an empty canvas - render every page rather than wait for
    # each one to be diagnosed as a shell.
    Recipe(option="render", value="always", reason="why_render_sharepoint",
           stacks=("sharepoint",), kinds=(KIND_SITE,)),
    # The site knows its pages: they are items in a library. Following links
    # finds only what the navigation and the editors linked.
    Recipe(option="page_tree", value="sharepoint",
           reason="why_page_tree_sharepoint", stacks=("sharepoint",),
           kinds=(KIND_SITE,), without_repo=True),
    # One host serves every site of the tenant; the run is about one of them.
    Recipe(option="site_scope", value=lambda target: _sharepoint_scope(target),
           reason="why_site_scope_sharepoint", stacks=("sharepoint",),
           kinds=(KIND_SITE,), without_repo=True),
)


def _sharepoint_scope(target: str) -> str:
    import project_profile

    return project_profile.sharepoint_site_path(target)


@dataclass(frozen=True)
class Prompt:
    """A field this target makes worth asking for.

    Distinct from a `Suggestion`: a suggestion sets a value, a prompt asks
    for one the tool cannot supply. An SPFx checkout knows it ships web
    parts and cannot know **where** - the site is a person's answer, and
    without it `--web-parts` has nothing to confine.
    """
    field: str
    reason: str
    stack: str = ""
    evidence: str = ""


#: Fields a stack makes worth asking for, keyed the way `Suggestion` is.
PROMPTS = (
    Recipe(option="site_url", value=None, reason="why_spfx_site_url",
           stacks=("spfx",), kinds=(KIND_REPO,)),
    # A SharePoint site without a stored session answers every address with
    # Microsoft's sign-in page. Asked for only when there is no session -
    # see `build` - because the tool cannot sign in for the person.
    Recipe(option="sign_in", value=None, reason="why_sign_in_sharepoint",
           stacks=("sharepoint",), kinds=(KIND_SITE,)),
)


@dataclass
class Plan:
    """What this target is, and what it asks the run to do."""
    kind: str = KIND_SITE
    target: str = ""
    #: `project_profile.Profile` of the target when it is a folder, or of the
    #: checkout paired with a site. `None` when there is neither.
    profile: object = None
    suggestions: tuple = ()
    #: Fields worth asking for that the kind alone would not show.
    prompts: tuple = ()
    #: Every self-contained project found under a folder target, nearest
    #: first. One entry (or none) is the ordinary case; more than one is the
    #: question a folder of several solutions has to be asked - see
    #: `project_profile.projects`.
    projects: list = field(default_factory=list)
    #: Every dev server this target could start - `devserver.Server`. A
    #: monorepo answers with the root's own and one per application, and the
    #: two are different runs: the root's `dev` script serves the workspace,
    #: an application's serves that application. See `devserver.servers_under`.
    servers: list = field(default_factory=list)

    def fields(self) -> tuple:
        return fields_for(self.kind)

    def applies(self, option: str) -> bool:
        return applies(option, self.kind)

    def suggestion(self, option: str):
        """The suggestion for `option`, or `None`."""
        for item in self.suggestions:
            if item.option == option:
                return item
        return None

    def asks_for(self, name: str) -> bool:
        """Should this surface offer the `name` field?"""
        return any(prompt.field == name for prompt in self.prompts)

    def stacks(self) -> list:
        return [stack.name for stack in getattr(self.profile, "stacks", ())]

    def ambiguous(self) -> bool:
        """Does this folder hold more than one project?"""
        return len(self.projects) > 1

    def choices(self) -> list:
        """What `--project` accepts here: the last component of each root.

        Names rather than paths, because that is what a person reads off a
        folder and types back. Two projects with the same last component are
        possible in a deep tree, and `resolve_project` answers that by taking
        a path as well.
        """
        from pathlib import Path as _Path

        return [_Path(profile.root).name for profile in self.projects]

    def shared_server(self):
        """The workspace server, when this target is a monorepo root.

        `None` for an ordinary project. A monorepo root that can serve
        itself is the case the `--devserver` flag was silently deciding: its
        script starts, or orchestrates, the applications under it, and each
        of those has a server of its own.
        """
        for server in self.servers:
            if server.workspace and server.root == self.target:
                return server
        return None

    def project_servers(self) -> list:
        """The dev servers that belong to a project rather than to the root."""
        return [server for server in self.servers
                if server.root != self.target]

    def apply(self, args, touched=()) -> list:
        """Set what this target asks for on `args`, and say what was set.

        `touched` is every option the person set by hand. A suggestion never
        overwrites one: the risk this whole feature carries is a default
        that quietly undoes a deliberate choice, and the mitigation is that
        the choice always wins.

        Returns the applied suggestions, so the caller can print "enabled,
        because …" for each. Nothing is applied silently and there is no way
        to call this that applies something silently.
        """
        applied = []
        touched = set(touched or ())
        for item in self.suggestions:
            if item.option in touched:
                continue
            if not self.applies(item.option):
                continue
            if getattr(args, item.option, None) == item.value:
                # Already what it asks for - true of a default that agrees.
                # Not reported: "enabled, because" would be a lie about a
                # value nobody changed.
                continue
            setattr(args, item.option, item.value)
            applied.append(item)
        return applied


def _profile_for(path: str):
    import project_profile
    try:
        return project_profile.detect(path)
    except OSError:
        return None


def _site_profile(target: str):
    """What the address alone proves, or `None`: today, SharePoint Online."""
    import project_profile

    if not project_profile.is_sharepoint_online(target):
        return None
    return project_profile.detect_from_url(target)


def _merged(first, second):
    """Two profiles as one: the site's stacks, then the checkout's."""
    if first is None:
        return second
    if second is None:
        return first
    import project_profile

    merged = project_profile.Profile(root=getattr(second, "root", ""))
    for source in (first, second):
        for stack in source.stacks:
            if stack.name not in merged.evidence:
                merged.stacks.append(stack)
                merged.evidence[stack.name] = source.evidence.get(stack.name, "")
                merged.versions[stack.name] = source.versions.get(stack.name, "")
    return merged


def _has_session(target: str) -> bool:
    import site_session

    try:
        return site_session.has_session(site_session.host_of(target))
    except Exception:  # noqa: BLE001 - a session that cannot be read is none
        return False


def build(target: str, profile=None, forced_url: bool = False,
          projects=None, repo: str = "", repo_profile=None,
          signed_in=None) -> Plan:
    """What to do about this target.

    `profile` and `projects` are passed in rather than detected here when the
    caller already has them - the window detects once per folder and keeps
    the answer, and re-walking the tree per repaint is exactly the filesystem
    work that detection was moved off the paint path to avoid.

    `repo` is the checkout behind a site (`--repo`). Its stacks count as this
    run's stacks: a SharePoint page is not an SPFx project, and the thing
    that knows it ships web parts is the repository, not the address. The
    address itself counts too where it proves something on its own: a
    `*.sharepoint.com` host is SharePoint before a single page is read.

    `signed_in` says whether a session is stored for the site's host;
    `None` asks `site_session`. It only decides whether the sign-in prompt
    is shown.
    """
    target = (target or "").strip()
    repo = (repo or "").strip()
    kind = target_kind(target, forced_url=forced_url)
    if profile is None and kind == KIND_REPO and target:
        profile = _profile_for(target)
    if repo_profile is None and kind == KIND_SITE and repo:
        repo_profile = _profile_for(repo)
    if kind == KIND_SITE:
        profile = _merged(_site_profile(target) if target else None,
                          repo_profile)
    if projects is None and kind == KIND_REPO and target:
        import project_profile
        try:
            projects = project_profile.projects(target)
        except OSError:
            projects = []
    servers: list = []
    if kind == KIND_REPO and target:
        import devserver
        try:
            servers = devserver.servers_under(target, projects)
        except OSError:
            servers = []

    names = [stack.name for stack in getattr(profile, "stacks", ())]
    evidence = getattr(profile, "evidence", {}) or {}

    def _matches(recipe):
        """The stack that asked, or `None`. `""` means the kind asked."""
        if kind not in recipe.kinds:
            return None
        if recipe.without_repo and repo:
            return None
        if not recipe.stacks:
            return ""
        for name in names:
            if name in recipe.stacks:
                return name
        return None

    suggestions = []
    for recipe in RECIPES:
        name = _matches(recipe)
        if name is None:
            continue
        value = recipe.value(target) if callable(recipe.value) else recipe.value
        suggestions.append(Suggestion(
            option=recipe.option, value=value, reason=recipe.reason,
            stack=name, evidence=evidence.get(name, "")))
    prompts = []
    for recipe in PROMPTS:
        name = _matches(recipe)
        if name is None:
            continue
        if recipe.option == "sign_in":
            if signed_in is None:
                signed_in = _has_session(target)
            if signed_in:
                continue
        prompts.append(Prompt(field=recipe.option, reason=recipe.reason,
                              stack=name, evidence=evidence.get(name, "")))
    plan = Plan(kind=kind, target=target, profile=profile,
                suggestions=tuple(suggestions), prompts=tuple(prompts),
                projects=list(projects or []), servers=servers)
    # A monorepo root's dev server is not this project's dev server. Saying
    # "start it" without saying *which* is the flag deciding for the person
    # who asked for it, so the sentence changes rather than the value.
    if plan.shared_server() is not None and plan.project_servers():
        plan.suggestions = tuple(
            replace(item, reason="why_devserver_workspace")
            if item.option == "devserver" else item
            for item in plan.suggestions)
    return plan


def explain(item, lang: str = "en", enabled: bool = True) -> str:
    """One sentence: what switched on, and who asked for it.

    Here rather than in each surface because there are three of them and the
    sentence is the whole safeguard: a parameter that changes the run without
    saying why is the failure this module was written to avoid, and three
    copies of the wording is three chances for one of them to stop saying it.
    """
    from i18n.translations import t

    why = t(item.reason, lang)
    stack = getattr(item, "stack", "")
    evidence = getattr(item, "evidence", "")
    stem = "why_enabled" if enabled else "why_consider"
    if stack and evidence:
        return t(f"{stem}_stack", lang).format(
            why=why, stack=stack, evidence=evidence)
    return t(stem, lang).format(why=why)


def choose_project(plan, name: str) -> str:
    """The root of the project `name` picks out, or `""`.

    A folder of twenty SPFx solutions is twenty deliverables, and naming one
    is how a person audits one. Accepted spellings: the project's own folder
    name (`web`), a path relative to the target (`apps/web`), or an absolute
    path - because a form hands over a path and a person types a name, and
    refusing either would make one of the two surfaces wrong.

    Empty for a name nothing matches, so the caller can print the choices
    rather than silently audit the whole folder - which is the behaviour
    this whole feature exists to replace.
    """
    from pathlib import Path as _Path

    wanted = (name or "").strip().rstrip("/\\")
    if not wanted:
        return ""
    target = _Path(plan.target) if plan.target else None
    for profile in plan.projects:
        root = _Path(profile.root)
        if wanted.lower() == root.name.lower():
            return str(root)
        if str(root) == wanted or root == _Path(wanted):
            return str(root)
        if target is not None:
            try:
                if root.relative_to(target) == _Path(wanted):
                    return str(root)
            except ValueError:  # pragma: no cover - not under the target
                continue
    return ""
