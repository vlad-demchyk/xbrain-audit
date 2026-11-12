"""A repeated component is one issue, not a page counter or a style verdict."""
from dataclasses import replace
from unittest import mock

from audit.base import ADVISORY, Issue, issues_in_view
from audit.engine import AccessibilityResult, DocumentReport, analyze_document, analyze_pages
from audit.rules.accessibility import ControlName, ImageModernFormat
from cli import build_parser
from duplicates import group_issues
from models import PageResult
from report.model import from_accessibility


def issue(snippet, source='https://example.test/a', **values):
    return Issue(rule_id='control-name', severity='critical', snippet=snippet,
                 source=source, **values)


def counts(issues):
    result = AccessibilityResult(root='https://example.test', mode='web',
                                 documents=[DocumentReport(source=item.source, issues=[item])
                                            for item in issues])
    return len(group_issues(issues)), len(from_accessibility(result, 'en').grouped_findings())


def test_fluent_counters_and_attribute_order_do_not_split_a_header_control():
    findings = [
        issue('<button class="ms-Button root-205" id="notifications" type="button">'),
        issue('<button type="button" id="notifications" class="root-332 ms-Button">',
              source='https://example.test/b'),
    ]
    assert counts(findings) == (1, 1)


def test_report_prose_and_ready_fix_do_not_split_one_problem():
    findings = [issue('<button class="ms-Button root-205">'),
                issue('<button class="ms-Button root-332">', source='https://example.test/b')]
    result = AccessibilityResult(root='https://example.test', mode='web',
                                 documents=[DocumentReport(source=item.source, issues=[item])
                                            for item in findings])
    model = from_accessibility(result, 'en')
    model.findings[1] = replace(model.findings[1], found='Another description',
                                replacement='<button class="root-332">Name</button>')
    assert len(model.grouped_findings()) == 1
    assert model.grouped_findings()[0].occurrences == 2


def test_different_resources_meaningful_classes_and_zones_stay_separate():
    for first, second in [
        ('<img src="/12345678/a.png">', '<img src="/98765432/a.png">'),
        ('<img src="/11111111-2222-4333-8444-555555555555/a.png">',
         '<img src="/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee/a.png">'),
        ('<button class="ms-Button mt-4">', '<button class="ms-Button mt-8">'),
        ('<button class="root-205">', '<button class="root-332">'),
        ('<a href="/about"></a>', '<a href="/pricing"></a>'),
        ('<td headers="price tax">', '<td headers="price discount">'),
    ]:
        assert counts([issue(first), issue(second)]) == (2, 2)
    assert counts([issue('<button>', details={'zone': 'custom', 'zone_name': 'Header'}),
                   issue('<button>', details={'zone': 'custom', 'zone_name': 'Footer'})]) == (2, 2)


def test_outside_canvas_alias_keeps_the_same_component_identity():
    assert counts([issue('<button>', details={'zone': 'custom', 'zone_name': 'Header'}),
                   issue('<button>', details={'zone': 'custom', 'zone_name': 'Header (outside the canvas)'})]) == (1, 1)


def test_certainty_is_not_lost_when_grouping():
    assert counts([issue('<button>'), issue('<button>', confidence='needs-browser')]) == (2, 2)


def test_placeholder_is_a_fallback_name_not_a_nameless_control():
    for kind in ['text', 'search', 'email', 'url', 'tel', 'password']:
        report = analyze_document(f'<input type="{kind}" placeholder="Search documents">',
                                  'page.html', rules=[ControlName()])
        assert report.issues == []
    report = analyze_document('<input type="text"><button></button>',
                              'page.html', rules=[ControlName()])
    assert len(report.issues) == 2


def test_png_is_an_optimization_suggestion_not_a_measured_performance_defect():
    report = analyze_document('<img src="logo.png" alt="Example">', 'page.html',
                              rules=[ImageModernFormat()])
    assert report.issues[0].confidence == ADVISORY
    assert issues_in_view(report.issues) == []
    assert issues_in_view(report.issues, unsettled=True) == report.issues


def test_sharepoint_outer_module_does_not_reaudit_its_named_parts():
    markup = '''<div class="page_deadbeef">
      <div data-sp-feature-tag="HeaderWebPart web part (Header)"
           data-viewport-id="external"><button id="notifications"></button></div>
      <div data-sp-feature-tag="Rich Text Editor"><p>Content</p></div>
    </div>'''
    page = PageResult(url='https://example.sharepoint.com/sites/a', depth=0, raw_html=markup)
    result = analyze_pages([page], page.url, rules=[ControlName()], sharepoint=True, media=False)
    assert len(result.issues()) == 1
    assert result.issues()[0].details['zone_name'] == 'Header'


def test_text_analysis_is_opt_in_in_the_cli_and_analysis_request():
    from analysis_modes import AnalysisRequest

    assert not build_parser().parse_args(['fullscan', 'https://example.test']).ai_text
    assert build_parser().parse_args(['fullscan', 'https://example.test', '--ai-text']).ai_text
    assert not AnalysisRequest().wants_ai_patterns


def test_default_fullscan_never_calls_text_detectors(tmp_path):
    from cli_impl import fullscan

    target = tmp_path / 'page.html'
    target.write_text('<html lang="en"><title>Example</title><h1>Example</h1></html>')
    args = build_parser().parse_args(['fullscan', str(target), '--no-browser', '--no-update-check',
                                    '--report', str(tmp_path / 'report.json'),
                                    '--styled-report', str(tmp_path / 'report.html')])
    with mock.patch.object(fullscan, '_fullscan_report_paths', return_value=None), \
            mock.patch.object(fullscan, '_scan_local_target') as scan:
        fullscan.cmd_fullscan(args)
    scan.assert_not_called()


def test_ai_text_flag_runs_the_optional_text_pass(tmp_path):
    from cli_impl import fullscan

    target = tmp_path / 'page.html'
    target.write_text('<html lang="en"><title>Example</title><h1>Example</h1></html>')
    args = build_parser().parse_args(['fullscan', str(target), '--no-browser', '--ai-text',
                                    '--report', str(tmp_path / 'report.json'),
                                    '--styled-report', str(tmp_path / 'report.html')])
    with mock.patch.object(fullscan, '_fullscan_report_paths', return_value=None), \
            mock.patch.object(fullscan, '_scan_local_target', return_value=([], None, [])) as scan:
        fullscan.cmd_fullscan(args)
    scan.assert_called_once()


def test_fullscan_and_tui_count_one_problem_with_multiple_observations():
    from cli_impl.fullscan import _build_combined
    from types import SimpleNamespace
    from tui.screens.results import summary_rows

    findings = [issue('<button>'), issue('<button>', source='https://example.test/b')]
    payload = _build_combined(SimpleNamespace(), 'https://example.test', True, 'en',
                              None, [], findings)
    assert payload['audit']['distinct'] == payload['summary']['distinct_problems'] == 1
    rows = dict(summary_rows(payload))
    assert rows['accessibility'] == rows['distinct problems'] == '1'
    assert rows['occurrences'] == '2'
