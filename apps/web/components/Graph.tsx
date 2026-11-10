"use client";
import { ReactFlow, Background, Controls, type Node, type Edge } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { GraphNode, GraphEdge } from "@/lib/api";

const COLX: Record<string, number> = { hypothesis: 0, observation: 360, execution: 720 };
const COLOR: Record<string, string> = {
  hypothesis: "#6aa6ff", observation: "#39d98a", execution: "#ffcc66",
};

export default function Graph({ nodes, edges }: { nodes: GraphNode[]; edges: GraphEdge[] }) {
  const counts: Record<string, number> = {};
  const rfNodes: Node[] = nodes.map((n) => {
    const col = counts[n.type] ?? 0;
    counts[n.type] = col + 1;
    const dim = n.status === "refuted";
    return {
      id: n.id,
      position: { x: COLX[n.type] ?? 0, y: col * 70 },
      data: { label: n.label + (n.confidence != null ? ` (${n.confidence})` : "") },
      style: {
        background: "#0f1623",
        color: dim ? "#8aa0bd" : "#e6edf6",
        border: `1px solid ${COLOR[n.type] ?? "#223047"}`,
        borderStyle: dim ? "dashed" : "solid",
        borderRadius: 8, fontSize: 11, width: 300, padding: 6,
      },
    };
  });
  const rfEdges: Edge[] = edges.map((e, i) => ({
    id: `${e.src}->${e.dst}-${i}`,
    source: e.src, target: e.dst, label: e.rel,
    animated: e.rel === "supported_by",
    style: { stroke: e.rel === "refuted_by" ? "#ff6b6b" : "#39507a" },
    labelStyle: { fill: "#8aa0bd", fontSize: 9 },
  }));

  return (
    <div style={{ height: 420 }} className="rounded-lg border border-line bg-ink"
         role="img" aria-label="Provenance graph linking hypotheses to observations and real executions">
      <ReactFlow nodes={rfNodes} edges={rfEdges} fitView proOptions={{ hideAttribution: true }}>
        <Background color="#223047" gap={18} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
