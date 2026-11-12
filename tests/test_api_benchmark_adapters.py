"""Current vendor protocols without paid calls or invented localization evidence."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
import requests

from tests.test_validation_contract import sample
from validation import adapters, api_adapters as api, metrics


def public_sample(text="One measured sentence. Another measured sentence."):
    row = sample("public", text=text)
    row["provenance"]["public_benchmark"] = True
    return row


class Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(status_code=200, text=json.dumps(response))


def pangram(text="One measured sentence. Another measured sentence."):
    first = "One measured sentence."
    return {"task_id": "job-1", "stage": "STAGE_SUCCESS", "version": "4.0", "text": text,
        "fraction_ai": .5, "fraction_ai_assisted": 0., "fraction_human": .5,
        "windows": [{"text": first, "label": "AI-Generated", "start_index": 0, "end_index": len(first),
                     "ai_assistance_score": .97, "confidence": "High"}]}


def copyleaks():
    return {"modelVersion": "v11.0", "summary": {"human": 0., "ai": 1.},
            "results": [{"classification": 2, "probability": .73, "matches": [
                {"text": {"chars": {"starts": [0], "lengths": [260]}}}]}],
            "scannedDocument": {"actualCredits": 1, "totalWords": 40}}


def gptzero():
    return {"documents": [{"document_classification": "MIXED", "class_probabilities": {"human": .1, "ai": .2, "mixed": .7},
        "sentences": [{"sentence": "One measured sentence.", "highlight_sentence_for_ai": True}]}]}


def test_vendor_score_meanings_are_not_conflated_with_localization_confidence():
    cp = api.parse_copyleaks(copyleaks(), "long text")
    assert cp["score"] == 1. and cp["section_evidence"][0]["confidence"] == .73
    assert not cp["localization_supported"] and cp["spans"] == []
    pg = api.parse_pangram(pangram(), public_sample()["text"])
    assert pg["score"] == .5 and pg["spans"][0]["score"] == .97
    gz = api.parse_gptzero(gptzero(), public_sample()["text"])
    assert gz["score"] == .2 and gz["class_probabilities"]["mixed"] == .7
    assert gz["actual_model_version"] is None  # Never echo a requested version as observed.


def test_normalized_vendor_text_does_not_invent_original_offsets():
    original = "One\u00a0measured sentence. Another measured sentence."
    result = api.parse_pangram(pangram(), original)
    assert result["status"] == "checked" and not result["localization_supported"]
    assert result["spans"] == []
    with pytest.raises(ValueError, match="different document"):
        api.parse_pangram(pangram("Entirely different text"), original)


def test_offsets_are_verified_as_codepoints_or_utf16_and_repeated_quotes_need_evidence():
    text = "😀 repeated repeated"
    assert api.quote_range(text, text, "repeated", 3, 11) == (2, 10)  # UTF-16 positions.
    assert api.quote_range(text, text, "repeated", 2, 10) == (2, 10)
    assert api.quote_range(text, text, "repeated") is None
    assert api.quote_range(text, "normalized", "repeated") is None


def test_document_scores_without_sentence_localization_stay_unknown_for_spans():
    data = gptzero();del data["documents"][0]["sentences"]
    result = api.parse_gptzero(data, public_sample()["text"])
    report = metrics.span_localization([{**public_sample(), **result, "gold_spans": [[0, 20]]}], .9)
    assert report["iou"] is None and report["unsupported_localization_samples"] == 1


def test_provider_labels_are_not_filtered_by_an_unrelated_document_threshold():
    result = api.parse_gptzero(gptzero(), public_sample()["text"])
    report = metrics.span_localization([{**public_sample(), **result, "gold_spans": [[0, 22]]}], .9)
    assert result["score"] == .2 and report["iou"] == 1.


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -.1, 1.1, True, ".9"])
def test_invalid_probabilities_are_rejected(value):
    with pytest.raises(ValueError):
        api.probability(value)


@pytest.mark.parametrize("change", [lambda d: d.update(fraction_human=.8),
    lambda d: d["windows"][0].update(label="New Unknown Label"),
    lambda d: d.update(stage="STAGE_FAILED"), lambda d: d.update(windows=[None])])
def test_malformed_pangram_result_cannot_become_checked(change):
    data=pangram();change(data)
    with pytest.raises(ValueError):
        api.parse_pangram(data, public_sample()["text"])


@pytest.mark.parametrize("name,config", [("copyleaks", {"expected_model_version": "v11.0"}),
    ("pangram", {"model": "pangram-4", "expected_model_version": "4.0"}),
    ("gptzero", {"request_version": "configured-version"})])
def test_missing_key_is_abstention_and_never_calls_network(monkeypatch, name, config):
    monkeypatch.delenv(api.KEY_ENV[name], raising=False)
    transport=Transport([])
    result=api.score_api_samples([public_sample()],name,config,allow_remote=True,session=transport)
    assert result[0]["status"] == "abstained" and result[0]["score"] is None
    assert transport.calls == []


def test_private_text_and_disabled_remote_never_construct_http_session(monkeypatch):
    monkeypatch.setattr(api.requests, "Session", lambda: pytest.fail("HTTP session constructed"))
    for row, allow in [(sample("private"), True), (public_sample(), False)]:
        with pytest.raises(ValueError, match="public benchmark"):
            adapters.score_samples([row], "gptzero", {"request_version": "configured-version"}, [], allow_remote=allow)


def test_pangram_submits_once_polls_same_job_and_does_not_publish_dashboard(monkeypatch,tmp_path):
    monkeypatch.setenv("PANGRAM_API_KEY","fixture-key")
    monkeypatch.setenv("XAUDIT_API_JOB_CACHE",str(tmp_path))
    monkeypatch.setattr(api,"sleep",lambda _:None)
    transport=Transport([{"task_id":"job-1"},{"task_id":"job-1","stage":"STAGE_PROCESSING"},pangram()])
    config={"model":"pangram-4","expected_model_version":"4.0"}
    result=api.score_api_samples([public_sample()],"pangram",config,allow_remote=True,session=transport)[0]
    assert result["status"] == "checked"
    assert [c[0] for c in transport.calls] == ["POST","GET","GET"]
    assert transport.calls[0][2]["json"]["public_dashboard_link"] is False
    assert all(c[2]["allow_redirects"] is False for c in transport.calls)
    again=Transport([pangram()])
    api.score_api_samples([public_sample()],"pangram",config,allow_remote=True,session=again)
    assert [c[0] for c in again.calls] == ["GET"]
    assert "fixture-key" not in json.dumps(result)
    assert all("fixture-key" not in p.read_text() for p in tmp_path.iterdir())


def test_unknown_submission_outcome_is_not_automatically_retried(monkeypatch,tmp_path):
    monkeypatch.setenv("PANGRAM_API_KEY","fixture-key")
    monkeypatch.setenv("XAUDIT_API_JOB_CACHE",str(tmp_path))
    config={"model":"pangram-4","expected_model_version":"4.0"}
    first=Transport([requests.Timeout("secret fixture-key")])
    result=api.score_api_samples([public_sample()],"pangram",config,allow_remote=True,session=first)[0]
    assert result["status"] == "error" and "fixture-key" not in json.dumps(result)
    second=Transport([])
    result=api.score_api_samples([public_sample()],"pangram",config,allow_remote=True,session=second)[0]
    assert result["status"] == "abstained" and second.calls == []


def test_model_version_drift_is_unknown_not_a_valid_comparison(monkeypatch):
    monkeypatch.setenv("COPYLEAKS_ACCESS_TOKEN","fixture-key")
    config={"expected_model_version":"v10.0"}
    result=api.score_api_samples([public_sample("a "*200)],"copyleaks",config,allow_remote=True,session=Transport([copyleaks()]))[0]
    assert result["status"] == "error" and result["score"] is None
    assert result["actual_model_version"] == "v11.0"


def test_copyleaks_short_text_is_not_submitted(monkeypatch):
    monkeypatch.setenv("COPYLEAKS_ACCESS_TOKEN","fixture-key")
    transport=Transport([])
    result=api.score_api_samples([public_sample()],"copyleaks",{"expected_model_version":"v11.0"},allow_remote=True,session=transport)[0]
    assert result["status"] == "abstained" and not transport.calls


@pytest.mark.parametrize("name,settings", [
    ("copyleaks", {"expected_model_version": "v11.0"}),
    ("pangram", {"model": "pangram-4", "expected_model_version": "4.0"}),
    ("gptzero", {"request_version": "fixture-request", "expected_model_version": "fixture-model"}),
])
def test_real_requests_transport_against_local_http_server(monkeypatch, tmp_path, name, settings):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    calls = []
    gz = gptzero()
    gz["version"] = "fixture-model"
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def respond(self, method):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)))) if method == "POST" else None
            calls.append((method, self.path, dict(self.headers), body))
            result = (copyleaks() if name == "copyleaks" else gz if name == "gptzero"
                      else {"task_id": "job-1"} if method == "POST" else pangram())
            output = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(output)))
            self.end_headers()
            self.wfile.write(output)
        def do_POST(self):
            self.respond("POST")
        def do_GET(self):
            self.respond("GET")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setitem(api.ENDPOINTS, name, f"http://127.0.0.1:{server.server_port}/fixture")
    monkeypatch.setenv(api.KEY_ENV[name], "local-fixture-key")
    monkeypatch.setenv("XAUDIT_API_JOB_CACHE", str(tmp_path))
    try:
        row = public_sample("a " * 200) if name == "copyleaks" else public_sample()
        result = api.score_api_samples([row], name, settings, allow_remote=True)[0]
        assert result["status"] == "checked" and result["actual_model_version"]
        assert calls[0][0] == "POST"
        assert calls[0][2]["Content-Type"] == "application/json"
        if name == "copyleaks":
            assert calls[0][2]["Authorization"] == "Bearer local-fixture-key"
            assert calls[0][1].endswith("/check") and calls[0][3]["sandbox"] is False
        else:
            assert calls[0][2]["x-api-key"] == "local-fixture-key"
        if name == "pangram":
            assert calls[0][3]["model"] == "pangram-4" and calls[0][3]["public_dashboard_link"] is False
            assert calls[1][0:2] == ("GET", "/fixture/job-1")
        if name == "gptzero":
            assert calls[0][3] == {"document": row["text"], "version": "fixture-request"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_pending_pangram_job_is_reused_and_poll_socket_timeout_respects_remaining_budget(monkeypatch, tmp_path):
    monkeypatch.setenv("PANGRAM_API_KEY", "fixture-key")
    monkeypatch.setenv("XAUDIT_API_JOB_CACHE", str(tmp_path))
    ticks = iter([0., 0., .2, 1.1, 1.2])
    monkeypatch.setattr(api, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(api, "sleep", lambda _: None)
    settings = {"model": "pangram-4", "expected_model_version": "4.0", "poll_timeout_seconds": 1}
    first = Transport([{"task_id": "job-1"}, {"stage": "STAGE_PROCESSING"}])
    result = api.score_api_samples([public_sample()], "pangram", settings, allow_remote=True, session=first)[0]
    assert result["status"] == "abstained" and result["task_id"] == "job-1"
    assert first.calls[1][2]["timeout"] == pytest.approx((.8, .8))
    monkeypatch.setattr(api, "monotonic", lambda: 0.)
    resumed = Transport([pangram()])
    result = api.score_api_samples([public_sample()], "pangram", settings, allow_remote=True, session=resumed)[0]
    assert result["status"] == "checked" and [c[0] for c in resumed.calls] == ["GET"]


@pytest.mark.parametrize("change", [lambda d: d["results"][0]["matches"][0]["text"].update(chars=[]),
                                     lambda d: d.update(scannedDocument="invalid")])
def test_malformed_nested_vendor_objects_are_errors_without_losing_batch(monkeypatch, change):
    monkeypatch.setenv("COPYLEAKS_ACCESS_TOKEN", "fixture-key")
    data = copyleaks();change(data)
    rows = [public_sample("a " * 200), public_sample("b " * 200)]
    result = api.score_api_samples(rows, "copyleaks", {"expected_model_version": "v11.0"},
                                   allow_remote=True, session=Transport([data, copyleaks()]))
    assert result[0]["status"] == "error" and result[0]["score"] is None
    assert result[1]["status"] == "checked"


def test_vendor_config_rejects_ignored_settings_and_secrets():
    for settings in ({"expected_model_version": "v11.0", "model": "ignored"},
                     {"expected_model_version": "v11.0", "api_key": "secret"}):
        with pytest.raises(ValueError, match="configuration"):
            api.validate_api_config("copyleaks", settings)
