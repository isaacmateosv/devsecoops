export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export type GraphNode = {
  id: string; type: string; label: string;
  status?: string; confidence?: number;
};
export type GraphEdge = { src: string; dst: string; rel: string };

export type Report = {
  artifact: {
    id: string; filename: string; sha256: string; size_bytes: number;
    media_type: string; created_at: string;
  };
  recon: {
    fmt: string; machine: string; num_symbols: number;
    notable_symbols: string[]; notable_strings: string[]; statically_linked: boolean;
  } | null;
  hypotheses: Array<{
    id: string; status: string; formula_name: string; statement: string;
    rationale: string; confidence: number; params: Record<string, string>;
    supporting_observation_ids: string[]; refuting_observation_ids: string[];
  }>;
  verification: {
    precision: number; num_cases: number; matches: number;
    unresolved_uncertainty: string; oracle_ref: string;
  } | null;
  findings: Array<{
    id: string; title: string; defect_class: string; severity: string;
    confidence: number; triggering_input: string; observed_output: string;
    expected_output: string; discrepancy: string; root_cause_hypothesis: string;
    technical_impact: string; business_impact: string; assumptions: string;
    remediation: string; regression_test_path: string | null;
    reproduction: { steps: string[]; execution_ids: string[] };
  }>;
  attempts: Array<{
    attack_class: string; outcome: string; inputs_summary: string; note: string | null;
  }>;
  graph: { nodes: GraphNode[]; edges: GraphEdge[] };
  comparison: {
    id: string; build_id: string; counts: Record<string, number>;
    release_counts: Record<string, number>; disclaimer: string;
    report_path: string | null;
    approved_divergences: Array<{ id: string; status: string; description: string; approved_by: string }>;
    cases: Array<{
      eligible_loss: string; legacy: string | null; modern: string; oracle: string;
      track_a_compatible: boolean; track_b_correct: boolean;
      classification: string; release_status: string; note: string | null;
    }>;
  } | null;
};

export async function runDemo(): Promise<Report> {
  const r = await fetch(`${API_BASE}/api/demo/run`, { method: "POST" });
  if (!r.ok) throw new Error(`pipeline failed: ${r.status}`);
  return r.json();
}
