import { GitPullRequestArrow } from "lucide-react";
import { useMemo } from "react";
import ReactFlow, { Background, Controls } from "reactflow";
import "reactflow/dist/style.css";
import { createReactFlowLayout } from "./graphLayout";

export function RepoGraphFlow({ graphData, selectedNode, onSelectNode }) {
  const { nodes, edges } = useMemo(
    () => createReactFlowLayout(graphData, selectedNode?.id),
    [graphData, selectedNode?.id],
  );

  return (
    <section className="repo-graph-panel">
      <div className="panel-header">
        <div>
          <h2>Dependency graph</h2>
          <p>{nodes.length} files / {edges.length} imports</p>
        </div>
        <span className="graph-icon" aria-hidden="true">
          <GitPullRequestArrow size={18} />
        </span>
      </div>

      <div className="graph-canvas repo-flow-canvas">
        {nodes.length ? (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            fitView
            fitViewOptions={{ padding: 0.18 }}
            minZoom={0.2}
            maxZoom={1.8}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable
            onNodeClick={(_, node) => onSelectNode?.(node.data.originalNode)}
          >
            <Background color="#d7dee8" gap={22} />
            <Controls showInteractive={false} />
          </ReactFlow>
        ) : (
          <div className="repo-flow-empty">No dependency graph data yet.</div>
        )}
      </div>
    </section>
  );
}
