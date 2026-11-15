"""Semantic corruption regressions: rebuild hashes and exports after injection."""

import hashlib
import json

import pytest

from causalbridge.discovery.anm_requests import ANMConfig
from causalbridge.discovery.contracts import RuntimePair
from causalbridge.discovery.evidence import select_pair
from causalbridge.evaluation.audit_native import audit_native
from causalbridge.evaluation.export import analysis_rows
from causalbridge.evaluation.integration import IntegratedRunner, build_native_packages
from causalbridge.evaluation.integration_demo import ScriptedNativeModel
from causalbridge.llm.client import Generation


def rechain(rows):
    previous = None
    for i, row in enumerate(rows):
        row["seq"], row["previous"] = i, previous
        payload = {k: row[k] for k in ("seq", "previous", "kind", "data")}
        row["digest"] = hashlib.sha256(
            json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            ).encode()
        ).hexdigest()
        previous = row["digest"]


@pytest.fixture
def setup_run(tmp_path):
    source = RuntimePair(
        case_id="D0001", variables=({"name": "One"}, {"name": "Two"}), rows=[(1.0, 2.0)] * 128
    )
    packages = build_native_packages(
        select_pair(source), tmp_path / "anm", ANMConfig(sampling_seed=262)
    )
    root = tmp_path / "run"
    runner = IntegratedRunner(
        root,
        model_identity="release-corruption-fixture",
        model_mode="scripted_fixture",
        identity_verified=True,
    )
    return root, runner, packages


def corrupt_release(root, manifest, releases):
    rows = [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]
    event = next(row for row in rows if row["kind"] == "native_released")
    event["data"]["released_direction"] = "A_to_B"
    matching = next(r for r in releases if r["key"] == event["data"]["key"])
    matching["released_direction"] = "A_to_B"
    rechain(rows)
    (root / "events.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    (root / "exports" / (manifest + "-s2.json")).write_text(json.dumps(releases))


@pytest.mark.parametrize("failure", ["generate", "parse", "binding", "checker_error"])
def test_corrupted_skipped_release_rejected(setup_run, monkeypatch, failure):
    root, runner, packages = setup_run

    class FailingModel(ScriptedNativeModel):
        def generate(self, messages, schema):
            if failure == "generate":
                raise TimeoutError("fixture")
            if failure == "parse":
                return Generation(text="not JSON", model="fixture")
            result = super().generate(messages, schema)
            if failure == "binding":
                reply = json.loads(result.text)
                reply["case_id"] = "wrong-case"
                return Generation(text=json.dumps(reply), model="fixture")
            return result

    run = runner.run(packages, FailingModel())
    if failure == "checker_error":
        import causalbridge.evaluation.integration as module

        def broken_checker(*args, **kwargs):
            raise ValueError("fixture checker failure")

        monkeypatch.setattr(module, "check_prediction", broken_checker)
    releases = runner.replay_s2(run["manifest_id"])
    assert all(r["released_direction"] is None and r["check"] is None for r in releases)
    clean = audit_native(root)
    assert clean["passed"], clean
    clean_rows = analysis_rows(run, releases)
    assert all(r["predicted_direction"] is None for r in clean_rows if r["condition"] == "S2")
    corrupt_release(root, run["manifest_id"], releases)
    audited = audit_native(root)
    assert not audited["passed"], audited
    expected = "s2_missing_check" if failure == "checker_error" else "s2_failed_parent"
    assert expected in {f["code"] for f in audited["findings"]}
    # The test must exercise semantic rejection, not stale transport hashes/exports.
    assert not {"journal_integrity", "s2_export"}.intersection(
        f["code"] for f in audited["findings"]
    )
    with pytest.raises(ValueError, match="Contradictory S2"):
        analysis_rows(run, releases)
