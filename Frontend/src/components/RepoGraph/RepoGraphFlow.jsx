import { GitPullRequestArrow } from "lucide-react";
import { useMemo } from "react";
import ReactFlow, { Background, Controls, Handle, Position } from "reactflow";
import "reactflow/dist/style.css";
import { createReactFlowLayout } from "./graphLayout";

function FileNode({ data }) {
  return (
    <div className={`repo-flow-node ${data.isSelected ? "selected" : ""}`} title={data.fullLabel || data.label}>
      <Handle className="repo-flow-handle" type="target" position={Position.Top} />
      <div className="repo-flow-node-accent" style={{ backgroundColor: data.color }} />
      <div className="repo-flow-node-copy">
        <span>{data.label}</span>
        <small>{data.group}</small>
      </div>
      <Handle className="repo-flow-handle" type="source" position={Position.Bottom} />
    </div>
  );
}

const nodeTypes = {
  fileNode: FileNode,
};

export function RepoGraphFlow({ graphData, selectedNode, onSelectNode }) {
  const { nodes, edges, width, height } = useMemo(
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
          <div className="repo-flow-stage" style={{ minWidth: width, minHeight: height }}>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              fitView
              fitViewOptions={{ padding: 0.14 }}
              minZoom={0.25}
              maxZoom={1.6}
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable
              panOnScroll
              zoomOnScroll
              onNodeClick={(_, node) => onSelectNode?.(node.data.originalNode)}
            >
              <Background color="#eef2f7" gap={36} />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
        ) : (
          <div className="repo-flow-empty">No dependency graph data yet.</div>
        )}
      </div>
    </section>
  );
}
