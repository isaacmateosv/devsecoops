"""DevSecOops API (Prompt 1 vertical slice).

Serves real backend state only: every response is read from Postgres and the
immutable artifact/execution store. No simulated timers or invented progress.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import bootstrap  # noqa: F401  (sets up monorepo import paths)

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import config
import ingestion
import orchestrator
import store

app = FastAPI(title="DevSecOops API", version="0.1.0")
# Dev CORS so the Next.js reveal (localhost:3000) can read real backend state.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
_worker: Optional[orchestrator.Worker] = None
STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.on_event("startup")
def _startup() -> None:
    global _worker
    config.ensure_dirs()
    store.init_schema()
    _worker = orchestrator.Worker()
    _worker.start()


@app.on_event("shutdown")
def _shutdown() -> None:
    if _worker:
        _worker.stop()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/artifacts")
async def upload_artifact(file: UploadFile = File(...)):
    data = await file.read()
    try:
        art = ingestion.ingest_artifact(data, file.filename or "upload.bin")
    except ingestion.IngestError as e:
        raise HTTPException(status_code=422, detail=str(e))
    store.insert_artifact(art)
    return art.model_dump(mode="json")


class JobRequest(BaseModel):
    artifact_id: str
    input_text: Optional[str] = None


@app.post("/api/jobs")
def create_job(req: JobRequest):
    if store.get_artifact(req.artifact_id) is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    inp = req.input_text.encode() if req.input_text is not None else None
    try:
        job = orchestrator.submit_execute_job(req.artifact_id, inp)
    except ingestion.IngestError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return job.model_dump(mode="json")


@app.post("/api/demo/seed")
def demo_seed():
    """One-click known synthetic fixture: ingest the demo binary + sample claims
    and queue a real execution job."""
    if not config.DEMO_ARTIFACT.exists():
        raise HTTPException(status_code=500, detail="demo artifact not built")
    art = ingestion.ingest_artifact(config.DEMO_ARTIFACT.read_bytes(), "xol_calc")
    store.insert_artifact(art)
    inp = config.DEMO_INPUT.read_bytes() if config.DEMO_INPUT.exists() else None
    job = orchestrator.submit_execute_job(art.id, inp)
    return {"artifact": art.model_dump(mode="json"), "job": job.model_dump(mode="json")}


@app.get("/api/artifacts")
def list_artifacts():
    return [a.model_dump(mode="json") for a in store.list_artifacts()]


@app.get("/api/artifacts/{artifact_id}")
def get_artifact(artifact_id: str):
    a = store.get_artifact(artifact_id)
    if not a:
        raise HTTPException(status_code=404, detail="not found")
    return a.model_dump(mode="json")


@app.get("/api/jobs")
def list_jobs():
    return [j.model_dump(mode="json") for j in store.list_jobs()]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    j = store.get_job(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="not found")
    return j.model_dump(mode="json")


@app.get("/api/executions/{execution_id}")
def get_execution(execution_id: str):
    e = store.get_execution(execution_id)
    if not e:
        raise HTTPException(status_code=404, detail="not found")
    return e.model_dump(mode="json")


@app.get("/api/artifacts/{artifact_id}/inspect")
def inspect(artifact_id: str):
    import tools
    if store.get_artifact(artifact_id) is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return tools.inspect_artifact(artifact_id).model_dump(mode="json")


@app.post("/api/artifacts/{artifact_id}/investigate")
def investigate(artifact_id: str):
    import inference, tools
    if store.get_artifact(artifact_id) is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    result = inference.investigate(artifact_id, tools.Budget())
    return {
        "artifact_id": artifact_id,
        "submitted_hypothesis_id": result.submitted_hypothesis_id,
        "coverage": result.coverage,
        "unresolved": result.unresolved,
        "hypotheses": [store.get_hypothesis(h).model_dump(mode="json") for h in result.hypothesis_ids],
    }


@app.get("/api/artifacts/{artifact_id}/hypotheses")
def hypotheses(artifact_id: str):
    return [h.model_dump(mode="json") for h in store.list_hypotheses(artifact_id)]


@app.get("/api/artifacts/{artifact_id}/graph")
def logic_graph(artifact_id: str):
    """Business-logic graph: hypothesis -> observations -> experiments(executions)."""
    nodes, edges = [], []
    seen_exp = set()
    for h in store.list_hypotheses(artifact_id):
        nodes.append({"id": h.id, "type": "hypothesis", "label": h.formula_name,
                      "status": h.status.value, "confidence": h.confidence})
        for oid in (h.supporting_observation_ids + h.refuting_observation_ids):
            o = store.get_observation(oid)
            if not o:
                continue
            nodes.append({"id": o.id, "type": "observation",
                          "label": f"{o.input_value}->{o.output_value}"})
            rel = "supported_by" if oid in h.supporting_observation_ids else "refuted_by"
            edges.append({"src": h.id, "dst": o.id, "rel": rel})
            edges.append({"src": o.id, "dst": o.execution_id, "rel": "observed_in"})
            if o.execution_id not in seen_exp:
                seen_exp.add(o.execution_id)
                nodes.append({"id": o.execution_id, "type": "execution", "label": "restricted run"})
    return {"nodes": nodes, "edges": edges}


@app.post("/api/hypotheses/{hypothesis_id}/verify")
def verify_hypothesis(hypothesis_id: str):
    import verifier
    try:
        v = verifier.verify(hypothesis_id)
    except verifier.NotSubmitted as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return v.model_dump(mode="json")


@app.get("/api/hypotheses/{hypothesis_id}/verification")
def get_verification(hypothesis_id: str):
    v = store.get_verification_for(hypothesis_id)
    if not v:
        raise HTTPException(status_code=404, detail="no verification yet")
    return v.model_dump(mode="json")


@app.get("/api/ai/status")
def ai_status():
    import agent
    return agent.ai_status().dict()


@app.post("/api/artifacts/{artifact_id}/redteam")
def redteam_scan(artifact_id: str):
    import redteam, tools
    from contracts import HypothesisStatus
    if store.get_artifact(artifact_id) is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    submitted = [h for h in store.list_hypotheses(artifact_id)
                 if h.status == HypothesisStatus.SUBMITTED]
    if not submitted:
        raise HTTPException(status_code=409,
                            detail="no submitted hypothesis; run /investigate first")
    res = redteam.scan(artifact_id, submitted[-1].id, tools.Budget(max_executions=48))
    return {
        "artifact_id": artifact_id,
        "findings": [store.get_finding(f).model_dump(mode="json") for f in res.finding_ids],
        "attempts": [a.model_dump(mode="json") for a in store.list_attempts(artifact_id)],
    }


@app.get("/api/artifacts/{artifact_id}/findings")
def findings(artifact_id: str):
    return [f.model_dump(mode="json") for f in store.list_findings(artifact_id)]


@app.get("/api/artifacts/{artifact_id}/attempts")
def attempts(artifact_id: str):
    return [a.model_dump(mode="json") for a in store.list_attempts(artifact_id)]


@app.get("/api/findings/{finding_id}")
def get_finding(finding_id: str):
    f = store.get_finding(finding_id)
    if not f:
        raise HTTPException(status_code=404, detail="not found")
    return f.model_dump(mode="json")


# ---- Prompt 4: modern replacement + verified modernization ----
class CalcRequest(BaseModel):
    eligible_loss: str


@app.post("/api/modern/calculate")
def modern_calculate(req: CalcRequest):
    import modern
    try:
        return modern.calculate(req.eligible_loss)
    except modern.ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/api/artifacts/{artifact_id}/compare")
def compare_impls(artifact_id: str):
    import compare, tools
    if store.get_artifact(artifact_id) is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    report = compare.compare(artifact_id, budget=tools.Budget(max_executions=4))
    return report.model_dump(mode="json")


@app.get("/api/artifacts/{artifact_id}/comparisons")
def list_comparisons(artifact_id: str):
    return [r.model_dump(mode="json") for r in store.list_comparisons(artifact_id)]


@app.get("/api/comparisons/{report_id}")
def get_comparison(report_id: str):
    r = store.get_comparison(report_id)
    if not r:
        raise HTTPException(status_code=404, detail="not found")
    return r.model_dump(mode="json")


@app.post("/api/demo/run")
def demo_run():
    """One-click full pipeline over the known synthetic fixture, all real:
    ingest -> source-blind investigation -> blinded verify -> red-team Oops ->
    verified modern replacement (Track A/B). Returns the aggregate report."""
    import inference, redteam, compare, verifier, tools
    art = ingestion.ingest_artifact(config.DEMO_ARTIFACT.read_bytes(), "xol_calc")
    store.insert_artifact(art)
    inv = inference.investigate(art.id, tools.Budget())
    verifier.verify(inv.submitted_hypothesis_id)
    redteam.scan(art.id, inv.submitted_hypothesis_id, tools.Budget(max_executions=48))
    compare.compare(art.id, budget=tools.Budget(max_executions=4))
    return _aggregate_report(art.id)


@app.get("/api/artifacts/{artifact_id}/report")
def report(artifact_id: str):
    if store.get_artifact(artifact_id) is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return _aggregate_report(artifact_id)


def _aggregate_report(artifact_id: str) -> dict:
    """Everything the five-act reveal and the exportable report need, sourced
    entirely from stored records."""
    import tools
    from contracts import HypothesisStatus
    art = store.get_artifact(artifact_id)
    hyps = store.list_hypotheses(artifact_id)
    submitted = next((h for h in hyps if h.status == HypothesisStatus.SUBMITTED), None)
    verification = store.get_verification_for(submitted.id) if submitted else None
    comparisons = store.list_comparisons(artifact_id)
    try:
        meta = tools.inspect_artifact(artifact_id).model_dump(mode="json")
    except Exception:
        meta = None
    return {
        "artifact": art.model_dump(mode="json"),
        "recon": meta,
        "hypotheses": [h.model_dump(mode="json") for h in hyps],
        "verification": verification.model_dump(mode="json") if verification else None,
        "findings": [f.model_dump(mode="json") for f in store.list_findings(artifact_id)],
        "attempts": [a.model_dump(mode="json") for a in store.list_attempts(artifact_id)],
        "graph": logic_graph(artifact_id),
        "comparison": comparisons[0].model_dump(mode="json") if comparisons else None,
    }


@app.get("/")
def index():
    idx = STATIC_DIR / "index.html"
    if idx.exists():
        return FileResponse(idx)
    return JSONResponse({"service": "devsecoops", "see": "/docs"})
