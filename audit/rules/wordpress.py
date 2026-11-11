"""The one check that is specific to a WordPress template and measurable.

A stack pack is easy to write and hard to justify. The plan for this module
listed five candidates - a missing `wp_head()`, a hardcoded `<script src>`
instead of `wp_enqueue_script`, a thumbnail with no alt, an unlabelled search
form, unescaped output - and four of them measured **zero** on the WordPress
code available here: the theme at `~/Local Sites/municipal-site` (two themes, 534
PHP files) calls `wp_head()` in every file that opens a `<head>`, enqueues
every script, and has no unlabelled search form. Shipping those four anyway
would grow the rule list without growing what the tool can find, which is the
way a rule list stops being trustworthy.

The fifth one measured **592**: 577 in the installed `design-comuni` theme
and 15 in the site's own `municipal_wp`. That is `WordPress.Security.
EscapeOutput` in WPCS terms, and it is the defect a WordPress review actually
finds.

**Why this reads the file rather than the parsed tree.** `<?php echo $x; ?>`
is a processing instruction to an HTML parser and carries no text, so
`repo_scanner.mask_server_tags` removes it before parsing - deliberately, or
a link whose text comes from the server would report as nameless. What this
rule is about is exactly that removed text, so it reads
`audit.base.document_source`, which is the file as it is on disk.
"""
from __future__ import annotations

import re

from ..base import (
    ADVISORY, BEST_PRACTICES, SERIOUS, Issue, Rule, RuleRegistry,
    document_source,
)

#: `<?php echo $thing; ?>` and `<?= $thing ?>`, where the whole expression is
#: one variable - possibly a property or an array element. Narrow on purpose:
#: `<?php echo $open ? 'is-open' : ''; ?>` chooses between two literals
#: written in the file and is safe, and it is by far the most common shape in
#: a template. Matching it too was 536 findings on this corpus, nearly all of
#: them wrong; requiring a bare variable leaves 592 that are real.
_ECHOED_VARIABLE = re.compile(
    r"<\?(?:php\s+|=\s*)(?:echo\s+)?"
    r"(\$[A-Za-z_]\w*(?:(?:->|::)\w+|\[[^\]\[]*\])*)"
    r"\s*;?\s*\?>")

#: Nothing that already escaped is matched, and no list is needed for that:
#: `esc_html($x)`, `wp_kses($x, ...)` and `absint($x)` are calls, and the
#: pattern above only matches a bare variable.


class WordPressUnescapedOutput(Rule):
    """A template variable printed straight into the markup.

    WordPress does not escape on output for you. Whatever is in that variable
    - a post meta field, a query argument, an option somebody with editor
    rights can set - is written into the page as markup, so a `<script>` or
    an `onerror` in it runs in every visitor's browser.

    Advisory, and filed under best practices rather than security, for the
    same reason as `jsx-dangerous-html`: the variable may have been escaped
    three lines earlier, and a static read of one file cannot follow it. The
    `security` category was opened on the condition that nothing in it
    infers, and spending that credibility here would cost more than this
    finding is worth. What the finding says is "escape at the point of
    output, where it can be seen" - which is what the WordPress coding
    standards say too.
    """
    id = "wp-unescaped-output"
    category = BEST_PRACTICES
    severity = SERIOUS
    confidence = ADVISORY
    stacks = ("wordpress", "wordpress-theme", "wordpress-plugin", "bedrock")

    def check(self, document, context) -> list:
        markup = document_source(document)
        if not markup or "<?" not in markup:
            return []
        issues = []
        seen = set()
        for match in _ECHOED_VARIABLE.finditer(markup):
            variable = match.group(1)
            line = markup.count("\n", 0, match.start()) + 1
            key = (variable, line)
            if key in seen:
                continue
            seen.add(key)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, line=line,
                snippet=match.group(0)[:120], source=context.source,
                category=self.category, confidence=self.confidence,
                details={"value": variable},
                fix_snippet=f"<?php echo esc_html({variable}); ?>",
            ))
        return issues


RuleRegistry.register(WordPressUnescapedOutput)
