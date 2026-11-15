"""Kris Phase 2: saved attempts, resume and model-free process-check replay.

No gold records, statistical estimation, automatic retries or scoring enter here.
Checker injection is a boundary; production checker adapters are Phase 4.
"""

import hashlib
from copy import deepcopy
from pathlib import Path
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from causalbridge.discovery.contracts import (
    DirectionProposal,
    EvidenceEnvelope,
    PredictionAttempt,
    ReleaseRecord,
)
from causalbridge.discovery.evidence import digest
from causalbridge.discovery.prompts import PROMPT_VERSION, output_schema, render
from causalbridge.evaluation.store import Journal, atomic_json
from causalbridge.llm.client import Generation, JSONModel, ModelConfig
from causalbridge.llm.parser import parse_json

RUNNER_VERSION = "kris-runner-v1.1"


class Checker(Protocol):
    version: str

    def check(
        self, envelope: EvidenceEnvelope, saved: PredictionAttempt, receipt: dict
    ) -> ReleaseRecord: ...


def _parse_attempt(start: dict, generation: Generation | None, error: str | None):
    proposal = None
    failure = error
    status = "model_error" if generation is None else "parsed"
    if generation is not None:
        try:
            proposal = parse_json(generation.text, DirectionProposal)
        except (ValueError, TypeError):
            status, failure = "parse_error", "structured_output_error"
    return PredictionAttempt(
        attempt_id=start["attempt_id"],
        evidence_digest=start["envelope"]["evidence_digest"],
        condition=start["condition"],
        status=status,
        raw_text=generation.text if generation else None,
        proposal=proposal,
        failure_code=failure,
        model=generation.model if generation else start["model_identity"],
        model_mode=start["model_mode"],
        input_tokens=generation.input_tokens if generation else None,
        output_tokens=generation.output_tokens if generation else None,
    )


class ExperimentRunner:
    def __init__(
        self,
        root: Path | str,
        *,
        model_identity: str,
        config: ModelConfig | None = None,
        model_mode="scripted_fixture",
        identity_verified=False,
    ):
        if not model_identity or model_mode not in {"live", "scripted_fixture"}:
            raise ValueError("Explicit model identity/mode required")
        package_root = Path(__file__).resolve().parents[1]
        self.source_digest = digest(
            {
                str(p.relative_to(package_root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(package_root.rglob("*.py"))
            }
        )
        self.store = Journal(root)
        self.identity = model_identity
        self.config = config
        self.mode = model_mode
        # Unverified identity cannot reuse model outputs across runner sessions.
        self.session = "verified" if identity_verified else uuid4().hex

    def _schedule(self, envelopes, replicate_id, retry_id):
        planned = []
        seen = set()
        for envelope in envelopes:
            envelope = EvidenceEnvelope.model_validate_json(envelope.model_dump_json())
            pair = (envelope.payload.case_id, envelope.payload.package)
            if pair in seen:
                raise ValueError("Duplicate case/package in schedule")
            seen.add(pair)
            for condition in ("S0", "S1"):
                messages = render(envelope, condition)
                identity = dict(
                    envelope=envelope.model_dump(mode="json"),
                    condition=condition,
                    messages=messages,
                    output_schema=output_schema(),
                    prompt_version=PROMPT_VERSION,
                    runner_version=RUNNER_VERSION,
                    source_digest=self.source_digest,
                    model_identity=self.identity,
                    model_mode=self.mode,
                    model_config=self.config.model_dump(mode="json") if self.config else None,
                    identity_scope=self.session,
                    replicate_id=replicate_id,
                    retry_id=retry_id,
                )
                planned.append(identity | {"key": digest(identity)})
        return planned

    def run(self, envelopes, model: JSONModel, *, replicate_id="0", retry_id=None):
        actual_config = getattr(model, "config", None)
        if actual_config != self.config:
            raise ValueError("Transport configuration differs from runner configuration")
        planned = self._schedule(envelopes, replicate_id, retry_id)
        manifest_key = digest([p["key"] for p in planned])
        new_calls = 0
        invocation_id = uuid4().hex
        new_keys = set()
        with self.store.locked():
            manifest = {
                "runner_version": RUNNER_VERSION,
                "manifest_id": manifest_key,
                "expected_keys": [p["key"] for p in planned],
                "trials": [
                    {
                        "key": p["key"],
                        "case_id": p["envelope"]["payload"]["case_id"],
                        "package": p["envelope"]["payload"]["package"],
                        "condition": p["condition"],
                    }
                    for p in planned
                ],
            }
            atomic_json(self.store.root / "manifests" / (manifest_key + ".json"), manifest)
            starts, raws, ends = (
                self.store.by_key(k) for k in ("started", "generated", "finished")
            )
            for item in planned:
                key = item["key"]
                if key in ends:
                    continue  # Includes failed attempts: never silently retry.
                if key in starts:
                    start = starts[key]
                    if key in raws:
                        raw = raws[key]
                        generation = Generation.model_validate(raw["generation"])
                        attempt = _parse_attempt(start, generation, None)
                        end = dict(
                            key=key,
                            attempt=attempt.model_dump(mode="json"),
                            execution_error=None,
                            recovered=True,
                            latency_seconds=raw["latency_seconds"],
                        )
                    else:
                        end = dict(
                            key=key,
                            attempt=None,
                            execution_error="interrupted_unknown",
                            recovered=True,
                            latency_seconds=None,
                        )
                    end["saved_attempt_digest"] = digest(end["attempt"])
                    self.store.append("finished", end)
                    ends[key] = end
                    continue
                prior = [
                    e
                    for e in starts.values()
                    if e["envelope"]["evidence_digest"] == item["envelope"]["evidence_digest"]
                    and e["condition"] == item["condition"]
                    and e["replicate_id"] == replicate_id
                ]
                start = item | {
                    "attempt_id": uuid4().hex,
                    "invocation_id": invocation_id,
                    "original_envelope_digest": digest(item["envelope"]),
                    "parent_attempt_id": prior[-1]["attempt_id"]
                    if retry_id is not None and prior
                    else None,
                }
                self.store.append("started", start)
                starts[key] = start
                begin = perf_counter()
                new_calls += 1
                new_keys.add(key)
                try:
                    generation = Generation.model_validate(
                        model.generate(
                            deepcopy(start["messages"]), deepcopy(start["output_schema"])
                        )
                    )
                except Exception as exc:
                    attempt = _parse_attempt(start, None, "model_error")
                    end = dict(
                        key=key,
                        attempt=attempt.model_dump(mode="json"),
                        execution_error=f"{type(exc).__name__}: {exc}",
                        recovered=False,
                        latency_seconds=perf_counter() - begin,
                    )
                else:
                    raw = dict(
                        key=key,
                        generation=generation.model_dump(mode="json"),
                        latency_seconds=perf_counter() - begin,
                    )
                    self.store.append("generated", raw)  # Durable BEFORE parsing/checking.
                    attempt = _parse_attempt(start, generation, None)
                    end = dict(
                        key=key,
                        attempt=attempt.model_dump(mode="json"),
                        execution_error=None,
                        recovered=False,
                        latency_seconds=perf_counter() - begin,
                    )
                end["saved_attempt_digest"] = digest(end["attempt"])
                self.store.append("finished", end)
                ends[key] = end
            result = {
                "manifest_id": manifest_key,
                "invocation_id": invocation_id,
                "new_model_calls": new_calls,
                "new_trial_keys": sorted(new_keys),
                "cached_or_recovered_trials": len(planned) - new_calls,
                "trials": [dict(start=starts[p["key"]], outcome=ends[p["key"]]) for p in planned],
            }

            def usage(keys, field):
                values = [ends[k]["attempt"][field] if ends[k]["attempt"] else None for k in keys]
                return sum(values) if all(v is not None for v in values) else None

            all_keys = {p["key"] for p in planned}
            result["new_usage"] = {f: usage(new_keys, f) for f in ("input_tokens", "output_tokens")}
            result["historical_usage"] = {
                f: usage(all_keys - new_keys, f) for f in ("input_tokens", "output_tokens")
            }
            result["monetary_cost"] = None
            self.store.append("invocation", {k: v for k, v in result.items() if k != "trials"})
            atomic_json(self.store.root / "invocations" / (invocation_id + ".json"), result)
            atomic_json(self.store.root / "exports" / (manifest_key + ".json"), result)
            return result

    def replay_s2(self, manifest_id: str, checker: Checker):
        """No model parameter. Evidence/receipt come from original journal entries."""
        with self.store.locked():
            starts, ends, releases = (
                self.store.by_key(k) for k in ("started", "finished", "released")
            )
            manifest_path = self.store.root / "manifests" / (manifest_id + ".json")
            import json

            manifest = json.loads(manifest_path.read_text())
            if digest(manifest["expected_keys"]) != manifest_id:
                raise ValueError("Manifest identity mismatch")
            records = []
            for key in manifest["expected_keys"]:
                start, end = starts[key], ends[key]
                if start["condition"] != "S1":
                    continue
                release_key = digest([key, digest(end), checker.version])
                if release_key in releases:
                    records.append(releases[release_key])
                    continue
                attempt = (
                    PredictionAttempt.model_validate(end["attempt"]) if end["attempt"] else None
                )
                entry = dict(
                    key=release_key,
                    source_key=key,
                    source_attempt_id=start["attempt_id"],
                    parent_outcome_digest=digest(end),
                    checker_version=checker.version,
                    release=None,
                    skip_reason=None,
                )
                if attempt is None or attempt.status != "parsed":
                    entry["skip_reason"] = "parent_prediction_failed"
                else:
                    envelope = EvidenceEnvelope.model_validate(start["envelope"])
                    # Receipt is read from the ORIGINAL saved request, not candidate output.
                    receipt = {
                        "original_evidence_digest": start["envelope"]["evidence_digest"],
                        "original_envelope_digest": start["original_envelope_digest"],
                        "parent_attempt_digest": end["saved_attempt_digest"],
                    }
                    try:
                        release = ReleaseRecord.model_validate(
                            checker.check(
                                envelope, attempt.model_copy(deep=True), deepcopy(receipt)
                            )
                        )
                        if (
                            release.parent_attempt_id != attempt.attempt_id
                            or release.parent_attempt_digest != digest(end["attempt"])
                            or release.checker_version != checker.version
                            or (
                                release.released_direction is not None
                                and release.released_direction
                                != attempt.proposal.predicted_direction
                            )
                        ):
                            raise ValueError("Checker changed parent identity/version/direction")
                        entry["release"] = release.model_dump(mode="json")
                    except Exception as exc:
                        entry["skip_reason"] = "checker_error"
                        entry["error"] = f"{type(exc).__name__}: {exc}"
                self.store.append("released", entry)
                records.append(entry)
            atomic_json(self.store.root / "exports" / (manifest_id + "-s2.json"), records)
            return records
