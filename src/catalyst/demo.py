from __future__ import annotations

import hashlib

from .catalog import Catalog
from .common import canonical, make_bundle


def seed(catalog: Catalog) -> dict:
    """Synthetic, explicitly labeled curves to exercise the viewer without model calls."""
    def publish(doc):
        snapshot, content = make_bundle({f"{doc['kind']}.json": canonical(doc)})
        catalog.publish(content)
        return snapshot
    problems = [
        publish({"schema_version": 1, "kind": "problem", "id": "demo-ecdsa-best",
                 "title": "ecdsa.fail · synthetic tier demonstration",
                 "description": "Fictional ECDSA curves, not verified circuits or official results.",
                 "metric": {"name": "avg_toffoli × peak_qubits", "direction": "minimize"}, "demo": True}),
    ]
    curves = {
        "demo-direct": [(5, 1000), (20, 800), (200, 700), (800, 650)],
        "demo-planner": [(10, 1500), (20, 1200), (200, 600), (3500, 300)],
        "demo-notes": [(5, 1300), (20, 1000), (200, 500), (900, 400)],
    }
    titles = {"demo-direct": "Direct approach", "demo-planner": "Planning approach", "demo-notes": "Curated notes"}
    harnesses = [
        publish({"schema_version": 1, "kind": "harness", "id": key, "title": titles[key],
                 "description": "Synthetic harness; this is not a measured research result.",
                 "agent": "demo", "scope": "Demonstration only", "demo": True})
        for key in curves
    ]
    count = 0
    for problem in problems:
        for harness in harnesses:
            for repetition in range(3):
                identity = f"{problem['id']}-{harness['id']}-{repetition}"
                delta = (repetition - 1) * 10
                observations = [{
                    "cost": cost,
                    "score": value + delta,
                    "kind": "synthetic",
                } for cost, value in curves[harness["id"]]]
                doc = {
                    "schema_version": 1, "kind": "run", "id": identity, "title": titles[harness["id"]],
                    "problem": {k: problem[k] for k in ("id", "version")},
                    "harness": {k: harness[k] for k in ("id", "version")},
                    "metric": problem["document"]["metric"], "model": "synthetic-demo-model",
                    "conditions": "demo-ecdsa-best-v2", "condition_label": "Synthetic tier demonstration",
                    "condition_details": {"synthetic": True}, "evidence": "demo",
                    "status": "completed", "observations": observations, "cost_known": True,
                    "total_cost": observations[-1]["cost"], "cost_unit": "normalized_model_usd",
                    "input_provenance": "synthetic", "starting_cost": 0,
                    "source_record_sha256": hashlib.sha256(identity.encode()).hexdigest(),
                }
                publish(doc)
                count += 1
    return {"problems": len(problems), "harnesses": len(harnesses), "runs": count, "evidence": "synthetic demo only"}
