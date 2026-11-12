# XBrain Audit for Claude Code

A personal plugin that teaches an agent to work with XBrain Audit: which command answers which question, how to read the result, how to audit behind a login and how to prove a fix. One skill, `xbrain-audit` (it runs the `xaudit` command); only its one-line description is in context until the work mentions XBrain Audit, a scan or an audit.

The plugin lives in this repository so it changes with the tool it describes. Its version follows `APP_VERSION` in `config.py`.

## Install once

```bash
claude plugin marketplace add ~/repositories/XAnalyze/integrations/claude-code
claude plugin install xbrain-audit@xbrain-audit
```

Installed before the rename as `xanalyze@xanalyze`? Remove that one first, then install as above:

```bash
claude plugin uninstall xanalyze@xanalyze
claude plugin marketplace remove xanalyze
```

It is a user-scope plugin: available in every project, loaded only on mention.

## Update after changing the skill

1. Edit `xbrain-audit/skills/xbrain-audit/SKILL.md` (and `references/`).
2. Raise `version` in both `.claude-plugin/marketplace.json` and `xbrain-audit/.claude-plugin/plugin.json` to the app's version.
3. `claude plugin marketplace update xbrain-audit && claude plugin update xbrain-audit@xbrain-audit`, then restart the session.

## Relation to the brain's skill

`brain-a11y-verify` (deployed by XBrain from the brain's L2 rules) is the accessibility procedure: what to trust, what to check by hand, WCAG 2.2 AA. This plugin is the tool. The procedure refers to the tool, not the other way round, so neither repeats the other.
