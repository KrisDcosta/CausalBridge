"""Read-only Phase 3 artifact audit. No runner, builder, store or checker imports.

JSON/hash/statistic checks below are a separate verification path. Schema classes
are reused only to validate record shapes; no generation or release rule is called.
"""

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

from causalbridge.discovery.contracts import (
    DirectionProposal,
    EvidenceEnvelope,
    PredictionAttempt,
    ReleaseRecord,
)
from causalbridge.evaluation.audit_policy import BASE, CAUTION, PROMPT_VERSION, QUESTION

AUDIT_VERSION = "artifact-audit-v1"


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _json(text):
    def invalid(value):
        raise ValueError("Nonfinite JSON: " + value)

    return json.loads(text, object_pairs_hook=_object, parse_constant=invalid)


def _canonical(value):
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Nonfinite number")
        return 0.0 if value == 0 else value
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_canonical(v) for v in value]
    return value


def _hash(value):
    raw = json.dumps(
        _canonical(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _public(payload):
    # Mirrors the *specified* public allowlist, not a builder helper.
    allowed = {
        "schema_version",
        "task",
        "case_id",
        "package",
        "question",
        "context",
        "display_rows",
        "summary",
        "method",
        "evidence_ids",
    }
    if set(payload) - allowed:
        raise ValueError("Unexpected public field")

    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if v is not None}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    return strip(payload)


class Auditor:
    def __init__(self, root):
        self.root = Path(root)
        self.findings = []
        self.counts = {"events": 0, "trials": 0, "manifests": 0, "s2_records": 0}

    def check(self, valid, code, location):
        if not valid:
            self.findings.append({"code": code, "location": str(location)})
        return bool(valid)

    def guarded(self, action, code, location):
        try:
            action()
        except (ValueError, TypeError, KeyError, IndexError, OSError, AttributeError) as exc:
            self.findings.append(
                {"code": code, "location": str(location), "detail": type(exc).__name__}
            )

    def evidence(self, envelope, location):
        EvidenceEnvelope.model_validate(envelope)
        p = envelope["payload"]
        public = _public(p)
        self.check(p["question"] == QUESTION, "question_policy", location)
        self.check(_hash(public) == envelope["evidence_digest"], "evidence_digest", location)
        rows = [r["values"] for r in p["display_rows"]]
        if rows:
            expected = _hash({"convention": "ordered-ab-float-v1", "rows": rows})
            self.check(expected == envelope["display_sample_digest"], "display_digest", location)
            for axis in range(2):
                values = [r[axis] for r in rows]
                n = len(values)
                avg = math.fsum(values) / n
                sd = math.sqrt(math.fsum((v - avg) ** 2 for v in values) / n)
                summary = p["summary"][axis]
                expected = dict(
                    n=n, minimum=min(values), maximum=max(values), mean=avg, population_std=sd
                )
                self.check(
                    all(
                        math.isclose(summary[k], v, rel_tol=1e-12, abs_tol=1e-12)
                        for k, v in expected.items()
                    ),
                    "summary_values",
                    location,
                )
        else:
            self.check(envelope["display_sample_digest"] is None, "display_digest", location)
        if p["method"]:
            self.check(
                p["method"]["sample_digest"] == envelope["method_sample_digest"],
                "method_sample_binding",
                location,
            )
        else:
            self.check(envelope["method_sample_digest"] is None, "method_sample_binding", location)

    def trial(self, start, raw, end, location):
        self.counts["trials"] += 1
        identity = {
            k: v
            for k, v in start.items()
            if k
            not in {
                "key",
                "attempt_id",
                "original_envelope_digest",
                "parent_attempt_id",
                "invocation_id",
            }
        }
        self.check(_hash(identity) == start["key"], "cache_identity", location)
        self.check(
            _hash(start["envelope"]) == start["original_envelope_digest"],
            "original_receipt",
            location,
        )
        self.evidence(start["envelope"], location)
        messages = start["messages"]
        self.check(
            start["prompt_version"] == PROMPT_VERSION
            and messages[0]["content"] == BASE + (CAUTION if start["condition"] == "S1" else ""),
            "prompt_policy",
            location,
        )
        self.check(
            start["output_schema"] == DirectionProposal.model_json_schema(),
            "output_schema_policy",
            location,
        )
        self.check(
            len(messages) == 2 and [m["role"] for m in messages] == ["system", "user"],
            "prompt_roles",
            location,
        )
        self.check(
            _json(messages[1]["content"]) == _public(start["envelope"]["payload"]),
            "prompt_payload",
            location,
        )
        self.check(start["condition"] in {"S0", "S1"}, "model_condition", location)
        self.check(
            end["saved_attempt_digest"] == _hash(end["attempt"]), "saved_attempt_digest", location
        )
        attempt = end["attempt"]
        if attempt is None:
            self.check(
                end["execution_error"] == "interrupted_unknown" and raw is None,
                "unknown_attempt_state",
                location,
            )
            return
        PredictionAttempt.model_validate(attempt)
        self.check(
            attempt["attempt_id"] == start["attempt_id"]
            and attempt["evidence_digest"] == start["envelope"]["evidence_digest"]
            and attempt["condition"] == start["condition"]
            and attempt["model_mode"] == start["model_mode"],
            "attempt_binding",
            location,
        )
        if raw is None:
            self.check(
                attempt["status"] == "model_error" and attempt["raw_text"] is None,
                "missing_raw_generation",
                location,
            )
            return
        gen = raw["generation"]
        self.check(
            attempt["raw_text"] == gen["text"]
            and attempt["model"] == gen["model"]
            and all(attempt[f] == gen[f] for f in ("input_tokens", "output_tokens")),
            "raw_generation_binding",
            location,
        )
        try:
            parsed = DirectionProposal.model_validate(_json(gen["text"])).model_dump(mode="json")
        except ValueError:
            self.check(
                attempt["status"] == "parse_error" and attempt["proposal"] is None,
                "parse_failure_state",
                location,
            )
        else:
            self.check(
                attempt["status"] == "parsed" and attempt["proposal"] == parsed,
                "raw_proposal_mismatch",
                location,
            )

    def release(self, entry, starts, ends, location):
        self.counts["s2_records"] += 1
        key = entry["source_key"]
        start, end = starts[key], ends[key]
        self.check(start["condition"] == "S1", "s2_non_s1_parent", location)
        self.check(
            entry["source_attempt_id"] == start["attempt_id"]
            and entry["parent_outcome_digest"] == _hash(end),
            "s2_parent_binding",
            location,
        )
        self.check(
            entry["key"] == _hash([key, _hash(end), entry["checker_version"]]),
            "s2_cache_identity",
            location,
        )
        attempt, release = end["attempt"], entry["release"]
        usable = attempt is not None and attempt["status"] == "parsed"
        if not usable:
            self.check(
                release is None and entry["skip_reason"] == "parent_prediction_failed",
                "s2_failed_parent",
                location,
            )
        elif release is None:
            self.check(
                entry["skip_reason"] == "checker_error" and bool(entry.get("error")),
                "s2_missing_outcome",
                location,
            )
        else:
            ReleaseRecord.model_validate(release)
            self.check(
                entry["skip_reason"] is None
                and release["parent_attempt_id"] == attempt["attempt_id"]
                and release["parent_attempt_digest"] == _hash(attempt)
                and release["checker_version"] == entry["checker_version"],
                "s2_release_binding",
                location,
            )
            if release["process_status"] == "passed":
                p = start["envelope"]["payload"]
                proposal = attempt["proposal"]
                self.check(
                    set(proposal["evidence_refs"]) <= set(p["evidence_ids"]),
                    "passed_unavailable_citation",
                    location,
                )
                self.check(
                    proposal["claim_scope"] != "causal_proof", "passed_causal_proof_claim", location
                )
                attribution = proposal["method_attribution"]
                method = p["method"]
                expected = (
                    "unavailable"
                    if (
                        method is None or method["status"] == "error" or method["threshold"] is None
                    )
                    else (method["predicted_direction"] or "abstain")
                )
                self.check(
                    attribution is None or attribution == expected,
                    "passed_false_method_attribution",
                    location,
                )
            self.check(
                release["released_direction"] is None
                or release["released_direction"] == attempt["proposal"]["predicted_direction"],
                "s2_changed_arrow",
                location,
            )

    def matched(self, starts, keys, location, require_matrix):
        groups = {}
        for key in keys:
            start = starts[key]
            case = start["envelope"]["payload"]["case_id"]
            pair = (start["envelope"]["payload"]["package"], start["condition"])
            group = groups.setdefault(case, {})
            self.check(pair not in group, "duplicate_trial", location)
            group[pair] = start
        for case, group in groups.items():
            if require_matrix:
                self.check(
                    set(group) == {(e, c) for e in ("E1", "E2", "E3", "E4") for c in ("S0", "S1")},
                    "incomplete_matrix",
                    case,
                )
            reference = None
            context = None
            for (package, condition), start in group.items():
                p = start["envelope"]["payload"]
                if package != "E1":
                    numeric = [p["display_rows"], p["summary"]]
                    self.check(reference is None or reference == numeric, "matched_numeric", case)
                    reference = numeric
                if package != "E2":
                    self.check(context is None or context == p["context"], "matched_context", case)
                    context = p["context"]
                other = group.get((package, "S0"))
                if condition == "S1" and other:
                    self.check(
                        start["envelope"] == other["envelope"]
                        and start["output_schema"] == other["output_schema"]
                        and start["model_config"] == other["model_config"]
                        and start["model_identity"] == other["model_identity"],
                        "prompt_condition_isolation",
                        case,
                    )
                    s0, s1 = other["messages"], start["messages"]
                    self.check(
                        s0[1] == s1[1]
                        and s1[0]["content"].startswith(s0[0]["content"])
                        and len(s1[0]["content"]) > len(s0[0]["content"]),
                        "caution_only_intervention",
                        case,
                    )

    def invocation(self, event, starts, ends):
        invocation_id = event["invocation_id"]
        path = self.root / "invocations" / (invocation_id + ".json")
        exported = _json(path.read_text())
        self.check(
            {k: v for k, v in exported.items() if k != "trials"} == event, "invocation_export", path
        )
        keys = {trial["start"]["key"] for trial in exported["trials"]}
        self.check(
            all(
                trial
                == {"start": starts[trial["start"]["key"]], "outcome": ends[trial["start"]["key"]]}
                for trial in exported["trials"]
            ),
            "invocation_trial_binding",
            path,
        )
        new = {k for k, start in starts.items() if start.get("invocation_id") == invocation_id}
        self.check(
            set(event["new_trial_keys"]) == new
            and new <= keys
            and len(event["new_trial_keys"]) == len(new)
            and event["new_model_calls"] == len(new)
            and event["cached_or_recovered_trials"] == len(keys - new),
            "invocation_call_count",
            path,
        )
        for group, selected in (("new_usage", new), ("historical_usage", keys - new)):
            for field in ("input_tokens", "output_tokens"):
                values = [
                    ends[k]["attempt"][field] if ends[k]["attempt"] else None for k in selected
                ]
                expected = sum(values) if all(v is not None for v in values) else None
                self.check(event[group][field] == expected, "usage_accounting", path)
        self.check(event["monetary_cost"] is None, "uncomputed_cost", path)

    def provenance(self, starts):
        doc = _json((self.root / "provenance.json").read_text())
        self.check(doc["version"] == "selection-v1", "provenance_version", "provenance.json")
        cases = {}
        for item in doc["cases"]:
            source, sel = item["runtime_input"], item["selection"]
            case = source["case_id"]
            self.check(case not in cases, "duplicate_source_case", case)
            self.check(
                sel["case_id"] == case and sel["source_digest"] == _hash(source),
                "source_receipt",
                case,
            )
            spec = sel["spec"]

            def generator(seed, purpose, case=case):
                return random.Random(int(_hash([seed, case, purpose]), 16))

            order = [1, 0] if generator(spec["mapping_seed"], "mapping").getrandbits(1) else [0, 1]
            method = sorted(
                generator(spec["sample_seed"], "method").sample(
                    range(len(source["rows"])), min(spec["method_limit"], len(source["rows"]))
                )
            )
            display = sorted(
                generator(spec["display_seed"], "display").sample(
                    method, min(spec["display_limit"], len(method))
                )
            )
            self.check(
                sel["column_order"] == order
                and sel["method_indices"] == method
                and sel["display_indices"] == display,
                "selection_reproduction",
                case,
            )
            oriented = [[row[i] for i in order] for row in source["rows"]]
            method_rows = [oriented[i] for i in method]
            display_rows = [oriented[i] for i in display]
            cases[case] = (display_rows, [source["variables"][i] for i in order], method_rows)
        for start in starts.values():
            p = start["envelope"]["payload"]
            case = p["case_id"]
            rows, context, method_rows = cases[case]
            if p["package"] != "E1":
                self.check(
                    [r["values"] for r in p["display_rows"]] == rows, "source_display_mapping", case
                )
            if p["package"] != "E2":
                self.check(p["context"] == context, "source_context_mapping", case)
            if p["package"] == "E4":
                self.check(
                    p["method"]["sample_digest"]
                    == _hash({"convention": "ordered-ab-float-v1", "rows": method_rows})
                    and p["method"]["n_selected"] == len(method_rows),
                    "source_method_mapping",
                    case,
                )

    def run(self, require_matrix=True, require_s2=True, require_source=True):
        events = []

        def read_journal():
            raw = (self.root / "events.jsonl").read_bytes()
            self.check(not raw or raw.endswith(b"\n"), "partial_journal_tail", "events.jsonl")
            previous = None
            for index, line in enumerate(raw.splitlines()):
                event = _json(line)
                payload = {k: event[k] for k in ("seq", "previous", "kind", "data")}
                self.check(
                    set(event) == {*payload, "digest"}
                    and _hash(payload) == event["digest"]
                    and event["seq"] == index
                    and event["previous"] == previous,
                    "journal_integrity",
                    index,
                )
                events.append(event)
                previous = event["digest"]

        self.guarded(read_journal, "journal_unreadable", "events.jsonl")
        self.counts["events"] = len(events)
        maps = {kind: {} for kind in ("started", "generated", "finished", "released")}

        def fold(event):
            kind, data = event["kind"], event["data"]
            if not isinstance(data, dict):
                raise ValueError("Event data must be an object")
            if kind in maps:
                key = data.get("key")
                self.check(key is not None and key not in maps[kind], "duplicate_event", kind)
                if kind in {"generated", "finished"}:
                    self.check(key in maps["started"], "event_order", kind)
                    if kind == "generated":
                        self.check(key not in maps["finished"], "generation_after_finish", key)
                maps[kind][key] = data
            else:
                self.check(kind in {"invocation", "recovery"}, "unknown_event_kind", kind)

        for event in events:
            self.guarded(lambda e=event: fold(e), "invalid_event", event.get("seq", "unknown"))
        starts, raws, ends, releases = (maps[k] for k in maps)
        for key, start in starts.items():
            if self.check(key in ends, "unterminated_trial", key):
                self.guarded(
                    lambda s=start, k=key: self.trial(s, raws.get(k), ends[k], k),
                    "invalid_trial",
                    key,
                )
        for key, entry in releases.items():
            self.guarded(lambda e=entry, k=key: self.release(e, starts, ends, k), "invalid_s2", key)
        manifests = sorted((self.root / "manifests").glob("*.json"))
        self.check(bool(manifests), "no_manifests", "manifests")
        for path in manifests:
            self.counts["manifests"] += 1

            def inspect(path=path):
                m = _json(path.read_text())
                keys = m["expected_keys"]
                self.check(path.stem == m["manifest_id"] == _hash(keys), "manifest_identity", path)
                self.check(bool(keys) and len(keys) == len(set(keys)), "manifest_keys", path)
                self.check(all(k in starts and k in ends for k in keys), "missing_trial", path)
                for row, key in zip(m["trials"], keys, strict=True):
                    s = starts[key]
                    self.check(
                        row
                        == {
                            "key": key,
                            "case_id": s["envelope"]["payload"]["case_id"],
                            "package": s["envelope"]["payload"]["package"],
                            "condition": s["condition"],
                        },
                        "manifest_trial_binding",
                        path,
                    )
                self.matched(starts, keys, path, require_matrix)
                exported = _json((self.root / "exports" / (path.stem + ".json")).read_text())
                self.check(
                    exported["trials"] == [{"start": starts[k], "outcome": ends[k]} for k in keys],
                    "export_mismatch",
                    path,
                )
                if require_s2:
                    s2 = _json((self.root / "exports" / (path.stem + "-s2.json")).read_text())
                    expected = {k for k in keys if starts[k]["condition"] == "S1"}
                    self.check(
                        {e["source_key"] for e in s2} == expected and len(s2) == len(expected),
                        "s2_completeness",
                        path,
                    )
                    self.check(
                        all(releases.get(e["key"]) == e for e in s2), "s2_export_mismatch", path
                    )

            self.guarded(inspect, "manifest_or_export_invalid", path)
        for event in events:
            if event["kind"] == "invocation":
                self.guarded(
                    lambda e=event["data"]: self.invocation(e, starts, ends),
                    "invocation_invalid",
                    event["seq"],
                )
        if require_source:
            self.guarded(
                lambda: self.provenance(starts), "source_provenance_invalid", "provenance.json"
            )
        return {
            "audit_version": AUDIT_VERSION,
            "auditor_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "policy_digest": _hash(
                {"version": PROMPT_VERSION, "question": QUESTION, "base": BASE, "caution": CAUTION}
            ),
            "input_files_sha256": {
                str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(self.root.rglob("*"))
                if p.is_file() and p.name != "writer.lock"
            },
            "passed": not self.findings,
            "counts": self.counts,
            "findings": self.findings,
            "scope": {
                "require_matrix": require_matrix,
                "require_s2": require_s2,
                "require_source": require_source,
            },
            "limitations": [
                "Checks recorded evidence consistency, not causal correctness or ANM computation.",
                "Source receipts are producer-supplied, not authenticated.",
                "Cannot detect secrets or direction clues embedded in approved variable text.",
                "Journal cannot prove an unlogged external call did not occur.",
                "Hashes do not authenticate data against complete malicious rewriting.",
                "Checker semantics and unrestricted explanation support require separate review.",
            ],
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-partial-matrix", action="store_true")
    parser.add_argument("--without-s2", action="store_true")
    parser.add_argument("--without-source", action="store_true")
    args = parser.parse_args()
    root = args.input.resolve()
    output = args.output.resolve()
    # Auditing must never overwrite any input artifacts.
    if root == output or root in output.parents:
        parser.error("Audit report must be outside the input experiment directory")
    report = Auditor(root).run(
        not args.allow_partial_matrix, not args.without_s2, not args.without_source
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "counts": report["counts"],
                "findings": len(report["findings"]),
            }
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
