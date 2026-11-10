"use client";
import { useState } from "react";
import Graph from "@/components/Graph";
import { runDemo, type Report } from "@/lib/api";

/* ---------- small presentational helpers ---------- */
function Pill({ kind, children }: { kind: string; children: React.ReactNode }) {
  const map: Record<string, string> = {
    verified: "text-ok border-ok", approved_divergence: "text-warn border-warn",
    pending_approval: "text-warn border-warn", rejected: "text-bad border-bad",
    submitted: "text-ok border-ok", refuted: "text-bad border-bad",
    high: "text-bad border-bad", critical: "text-bad border-bad",
    observed: "text-warn border-warn", inferred: "text-acc border-acc",
  };
  return (
    <span className={`rounded-full border px-2 py-[2px] text-[11px] ${map[kind] ?? "text-mut border-line"}`}>
      {children}
    </span>
  );
}

function Act({ n, title, kicker, children }:
  { n: string; title: string; kicker: string; children: React.ReactNode }) {
  return (
    <section className="act mx-auto mb-6 w-full max-w-5xl rounded-xl border border-line bg-panel p-5">
      <div className="mb-3 flex items-baseline gap-3">
        <span className="text-xs tracking-widest text-acc">{n}</span>
        <h2 className="text-lg font-semibold">{title}</h2>
      </div>
      <p className="mb-4 text-sm text-mut">{kicker}</p>
      {children}
    </section>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex gap-3 border-b border-line py-1 text-sm last:border-0">
      <div className="w-40 shrink-0 text-mut">{k}</div>
      <div className="break-all">{v}</div>
    </div>
  );
}

/* ---------- page ---------- */
export default function Home() {
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    setBusy(true); setErr(null);
    try { setReport(await runDemo()); }
    catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  }

  function download() {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `devsecoops-report-${report.artifact.sha256.slice(0, 12)}.json`;
    a.click();
  }

  const f = report?.findings?.[0];
  const cmp = report?.comparison;

  return (
    <main className="min-h-screen px-4 py-8">
      <header className="mx-auto mb-6 w-full max-w-5xl">
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 className="text-2xl font-bold tracking-tight">DevSecOops</h1>
          <span className="text-sm text-mut">Financial Legacy Intelligence — the evidence trail</span>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-mut">
          <span>states:</span>
          <Pill kind="inferred">inferred</Pill>
          <Pill kind="observed">observed</Pill>
          <Pill kind="verified">verified</Pill>
        </div>
        <div className="no-print mt-4 flex flex-wrap gap-2">
          <button onClick={run} disabled={busy}
            className="rounded-lg bg-acc px-4 py-2 text-sm font-semibold text-ink disabled:opacity-50">
            {busy ? "Running real pipeline…" : report ? "Re-run" : "▶ Run live investigation"}
          </button>
          {report && (
            <>
              <button onClick={() => window.print()}
                className="rounded-lg border border-line px-4 py-2 text-sm text-acc">
                ⤓ Export report (PDF)
              </button>
              <button onClick={download}
                className="rounded-lg border border-line px-4 py-2 text-sm text-acc">
                ⤓ Download evidence (JSON)
              </button>
            </>
          )}
          {err && <span className="text-sm text-bad">{err}</span>}
        </div>
        {!report && !busy && (
          <p className="mt-4 max-w-2xl text-sm text-mut">
            One click runs the entire pipeline against the known synthetic fixture — every
            number below is read from stored records of actual executions. Nothing here is
            simulated. Point this UI at the API with <code>NEXT_PUBLIC_API_BASE</code>.
          </p>
        )}
      </header>

      {report && (
        <>
          {/* ACT I */}
          <Act n="ACT I" title="The Black Box" kicker="An undocumented financial executable and synthetic claims are ingested.">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-lg border border-line bg-panel2 p-4">
                <h3 className="mb-2 text-xs uppercase tracking-widest text-mut">Artifact</h3>
                <Row k="file" v={report.artifact.filename} />
                <Row k="type" v={report.artifact.media_type} />
                <Row k="size" v={`${report.artifact.size_bytes.toLocaleString()} bytes`} />
                <Row k="sha-256" v={<span className="text-[11px] text-mut">{report.artifact.sha256}</span>} />
              </div>
              <div className="rounded-lg border border-line bg-panel2 p-4">
                <h3 className="mb-2 text-xs uppercase tracking-widest text-mut">Static recon (LIEF)</h3>
                {report.recon ? (
                  <>
                    <Row k="format" v={`${report.recon.fmt} · ${report.recon.machine}`} />
                    <Row k="symbols" v={report.recon.num_symbols} />
                    <Row k="notable" v={<code className="text-acc">{report.recon.notable_symbols.join(", ")}</code>} />
                    <Row k="strings" v={<code className="text-acc">{report.recon.notable_strings.slice(0, 3).join(" | ")}</code>} />
                  </>
                ) : <p className="text-sm text-mut">recon unavailable</p>}
              </div>
            </div>
          </Act>

          {/* ACT II */}
          <Act n="ACT II" title="The Investigation" kicker="Agents probe the executable with real experiments and recover the candidate financial logic — with provenance.">
            <div className="mb-4 grid gap-3">
              {report.hypotheses.map((h) => (
                <div key={h.id} className="rounded-lg border border-line bg-panel2 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Pill kind={h.status}>{h.status}</Pill>
                    <code className="text-acc">{h.formula_name}</code>
                    <span className="text-xs text-mut">confidence {h.confidence}</span>
                  </div>
                  <p className="mt-2 text-sm">{h.statement}</p>
                  <p className="mt-1 text-xs text-mut">{h.rationale}</p>
                </div>
              ))}
            </div>
            {report.verification && (
              <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
                <Pill kind={report.verification.precision >= 1 ? "verified" : "rejected"}>
                  blinded precision {report.verification.precision}
                </Pill>
                <span className="text-mut">
                  {report.verification.matches}/{report.verification.num_cases} independent oracle cases ·
                  ⚠ {report.verification.unresolved_uncertainty}
                </span>
              </div>
            )}
            <Graph nodes={report.graph.nodes} edges={report.graph.edges} />
          </Act>

          {/* ACT III */}
          <Act n="ACT III" title="The Oops" kicker="A previously hidden defect is reproduced — actual input, actual output, independently expected output.">
            {f ? (
              <div className="rounded-lg border border-bad/40 bg-panel2 p-4">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <Pill kind={f.severity}>{f.severity}</Pill>
                  <b>{f.title}</b>
                  <span className="text-xs text-mut">confidence {f.confidence}</span>
                </div>
                <div className="grid gap-4 md:grid-cols-3">
                  <div className="rounded border border-line p-3 text-center">
                    <div className="text-xs text-mut">legacy observed</div>
                    <div className="text-2xl font-bold text-bad">${f.observed_output}</div>
                  </div>
                  <div className="rounded border border-line p-3 text-center">
                    <div className="text-xs text-mut">oracle expected</div>
                    <div className="text-2xl font-bold text-ok">${f.expected_output}</div>
                  </div>
                  <div className="rounded border border-line p-3 text-center">
                    <div className="text-xs text-mut">discrepancy</div>
                    <div className="text-sm">{f.discrepancy}</div>
                  </div>
                </div>
                <div className="mt-3">
                  <Row k="trigger" v={<code>{f.triggering_input}</code>} />
                  <Row k="root cause" v={f.root_cause_hypothesis} />
                  <Row k="business impact" v={f.business_impact} />
                  <Row k="assumptions" v={<span className="text-mut">{f.assumptions}</span>} />
                  <Row k="remediation" v={f.remediation} />
                  <Row k="regression test" v={<code className="text-acc">{f.regression_test_path}</code>} />
                  <Row k="reproduce" v={<span className="text-mut">{f.reproduction.steps.join(" → ")}</span>} />
                  <Row k="evidence" v={<span className="text-[11px] text-mut">executions {f.reproduction.execution_ids.join(", ")}</span>} />
                </div>
              </div>
            ) : <p className="text-sm text-mut">No verified Oops.</p>}
            <div className="mt-4">
              <h3 className="mb-2 text-xs uppercase tracking-widest text-mut">Red-team attempts (incl. unsuccessful)</h3>
              <div className="grid gap-1">
                {report.attempts.map((a, i) => (
                  <div key={i} className="flex flex-wrap items-center gap-2 text-sm">
                    <Pill kind={a.outcome === "no_discrepancy" ? "verified" : "rejected"}>{a.outcome}</Pill>
                    <span>{a.attack_class}</span>
                    <span className="text-xs text-mut">{a.inputs_summary}{a.note ? ` · ${a.note}` : ""}</span>
                  </div>
                ))}
              </div>
            </div>
          </Act>

          {/* ACT IV + V */}
          {cmp && (
            <Act n="ACT IV–V" title="The Rebuild & The Proof" kicker="A modern, overflow-safe service is built from approved requirements, then proven against legacy (Track A) and the independent oracle (Track B).">
              <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
                {Object.entries(cmp.release_counts).map(([k, v]) => (
                  <Pill key={k} kind={k}>{k} {v}</Pill>
                ))}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="text-mut">
                    <tr>
                      <th className="py-1 pr-3">eligible</th><th className="pr-3">legacy</th>
                      <th className="pr-3">modern</th><th className="pr-3">oracle</th>
                      <th className="pr-3">A</th><th className="pr-3">B</th><th>classification / release</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cmp.cases.map((c, i) => (
                      <tr key={i} className="border-t border-line">
                        <td className="py-1 pr-3">{c.eligible_loss}</td>
                        <td className="pr-3">{c.legacy ?? "—"}</td>
                        <td className="pr-3">{c.modern}</td>
                        <td className="pr-3">{c.oracle}</td>
                        <td className="pr-3">{c.track_a_compatible ? "✓" : "✗"}</td>
                        <td className="pr-3">{c.track_b_correct ? "✓" : "✗"}</td>
                        <td><Pill kind={c.release_status}>{c.classification}</Pill></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {cmp.approved_divergences.map((d) => (
                <p key={d.id} className="mt-3 text-sm text-warn">
                  ⚑ approved divergence <b>{d.id}</b> ({d.status}) — {d.description}
                </p>
              ))}
              <p className="mt-3 text-xs text-mut">{cmp.disclaimer}</p>
            </Act>
          )}

          <footer className="mx-auto w-full max-w-5xl py-6 text-center text-xs text-mut">
            Every figure above traces to a stored record of an actual execution. No simulated progress.
          </footer>
        </>
      )}
    </main>
  );
}
