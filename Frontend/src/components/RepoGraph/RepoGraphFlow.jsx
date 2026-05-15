import { GitPullRequestArrow, Maximize2, X } from "lucide-react";
import { useMemo, useState } from "react";
import ReactFlow, { Background, Controls, Handle, MiniMap, Position } from "reactflow";
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
  const [isExpanded, setIsExpanded] = useState(false);
  const { nodes, edges, width, height } = useMemo(
    () => createReactFlowLayout(graphData, selectedNode?.id),
    [graphData, selectedNode?.id],
  );

  const renderGraph = (expanded = false) => (
    <ReactFlow
      key={expanded ? "expanded-graph" : "embedded-graph"}
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      fitView
      fitViewOptions={{ padding: expanded ? 0.12 : 0.08, maxZoom: expanded ? 1.1 : 1.05 }}
      defaultViewport={{ x: 0, y: 0, zoom: expanded ? 1 : 0.9 }}
      minZoom={0.25}
      maxZoom={1.55}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable
      panOnScroll
      zoomOnScroll
      onNodeClick={(_, node) => onSelectNode?.(node.data.originalNode)}
    >
      <Background color="#f0f3f8" gap={48} />
      <MiniMap
        pannable
        zoomable
        nodeColor={(node) => node.data?.color || "#64748b"}
        nodeStrokeWidth={2}
      />
      <Controls showInteractive={false} />
    </ReactFlow>
  );

  return (
    <section className="repo-graph-panel">
      <div className="panel-header">
        <div>
          <h2>Dependency graph</h2>
          <p>{nodes.length} files / {edges.length} imports</p>
        </div>
        <div className="graph-header-actions">
          <button
            className="icon-text-button graph-expand-button"
            type="button"
            onClick={() => setIsExpanded(true)}
            disabled={!nodes.length}
          >
            <Maximize2 size={16} />
            Expand graph
          </button>
          <span className="graph-icon" aria-hidden="true">
            <GitPullRequestArrow size={18} />
          </span>
        </div>
      </div>

      <div className="graph-canvas repo-flow-canvas">
        {nodes.length ? (
          <>
          <div className="repo-flow-stage" style={{ minWidth: width, minHeight: height }}>
            {renderGraph(false)}
          </div>
          <div className="repo-flow-hint">Use Expand graph for large repositories.</div>
          </>
        ) : (
          <div className="repo-flow-empty">No dependency graph data yet.</div>
        )}
      </div>

      {isExpanded ? (
        <div className="graph-modal" role="dialog" aria-modal="true" aria-label="Expanded dependency graph">
          <div className="graph-modal-panel">
            <div className="graph-modal-header">
              <div>
                <h2>Dependency graph</h2>
                <p>{nodes.length} files / {edges.length} imports</p>
              </div>
              <button type="button" onClick={() => setIsExpanded(false)} aria-label="Close expanded graph">
                <X size={18} />
              </button>
            </div>
            <div className="graph-modal-canvas">
              <div className="repo-flow-stage expanded" style={{ minWidth: Math.max(width, 1200), minHeight: Math.max(height, 820) }}>
                {renderGraph(true)}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
