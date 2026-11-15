"""Sequential, process-locked, durable hash-chained experiment journal."""

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from causalbridge.discovery.evidence import canonical_json, digest


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    with temp.open("x", encoding="utf-8") as out:
        out.write(canonical_json(value) + "\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(temp, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


class Journal:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "events.jsonl"
        self.events = []

    @contextmanager
    def locked(self):
        with (self.root / "writer.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                self._load()
                yield self
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _load(self):
        self.events = []
        raw = self.path.read_bytes() if self.path.exists() else b""
        complete = raw.rfind(b"\n") + 1
        tail = raw[complete:]
        # Validate complete records before attempting any recovery mutation.
        for line in raw[:complete].splitlines():
            try:
                record = json.loads(line)
                payload = {k: record[k] for k in ("seq", "previous", "kind", "data")}
                if set(record) != {*payload, "digest"} or record["digest"] != digest(payload):
                    raise ValueError("Event integrity mismatch")
                expected_previous = self.events[-1]["digest"] if self.events else None
                if record["seq"] != len(self.events) or record["previous"] != expected_previous:
                    raise ValueError("Event order/chain mismatch")
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError("Corrupt completed journal record; refusing recovery") from exc
            self.events.append(record)
        if tail:
            recovery = self.root / ("quarantine-" + uuid4().hex + ".bin")
            with recovery.open("xb") as out:
                out.write(tail)
                out.flush()
                os.fsync(out.fileno())
            with self.path.open("r+b") as out:
                out.truncate(complete)
                out.flush()
                os.fsync(out.fileno())
            self.append(
                "recovery",
                {
                    "quarantine": recovery.name,
                    "byte_count": len(tail),
                    "tail_sha256": digest(list(tail)),
                },
            )

    def append(self, kind: str, data: dict):
        payload = dict(
            seq=len(self.events),
            previous=self.events[-1]["digest"] if self.events else None,
            kind=kind,
            data=data,
        )
        record = payload | {"digest": digest(payload)}
        with self.path.open("a", encoding="utf-8") as out:
            out.write(canonical_json(record) + "\n")
            out.flush()
            os.fsync(out.fileno())
        self.events.append(record)
        return record

    def by_key(self, kind: str) -> dict:
        found = {}
        for event in self.events:
            if event["kind"] != kind:
                continue
            data = event["data"]
            key = data["key"]
            if key in found:
                raise ValueError("Duplicate journal outcome: " + kind)
            found[key] = data
        return found
