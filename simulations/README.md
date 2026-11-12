# Simulations

Test fixtures for XBrain Audit. Each folder contains HTML files with specific issues.

## Folders

| Folder | Description |
|---|---|
| `ai-text/` | AI-generated content with clichés and structural patterns |
| `bad-accessibility/` | WCAG violations: missing alt, labels, contrast, headings |
| `bad-viewport/` | Responsive issues: fixed widths, small text, tiny touch targets |
| `bad-seo/` | SEO problems: missing title, meta, canonical, structured data |
| `bad-performance/` | Performance issues: render-blocking, large images, sync scripts |
| `mixed-problems/` | Combination of all issues |
| `good-site/` | Clean site with no issues (control) |

## Usage

```bash
# Test all simulations
xaudit fullscan simulations/ --json

# Test specific folder
xaudit scan simulations/ai-text/ --detector offline --json

# Test with browser
xaudit audit simulations/ --browser --breakpoints all --json

# Generate reports
xaudit fullscan simulations/ --styled-report report.html --report agent.md --json
```

## Expected Results

- `ai-text/` — Should find AI patterns (clichés, structural patterns)
- `bad-accessibility/` — Should find WCAG violations
- `bad-viewport/` — Should find responsive issues
- `bad-seo/` — Should find SEO problems
- `bad-performance/` — Should find performance issues
- `mixed-problems/` — Should find all types of issues
- `good-site/` — Should find minimal or no issues
