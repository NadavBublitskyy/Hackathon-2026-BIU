import { GitPullRequestArrow } from "lucide-react";
import { useMemo } from "react";
import { createGraphLayout } from "../../utils/graph";

const WIDTH = 880;
const HEIGHT = 620;

const nodeColor = (group) => {
  const palette = ["#2563eb", "#0f766e", "#b45309", "#7c3aed", "#be123c", "#15803d", "#4338ca"];
  const value = [...String(group || "root")].reduce((sum, char) => sum + char.charCodeAt(0), 0);

  return palette[value % palette.length];
};

export function RepoGraph({ graphData, selectedNode, onSelectNode }) {
  const positionedNodes = useMemo(() => createGraphLayout(graphData, WIDTH, HEIGHT), [graphData]);
  const nodeMap = useMemo(() => new Map(positionedNodes.map((node) => [node.id, node])), [positionedNodes]);
  const edges = graphData.edges || [];

  return (
    <section className="repo-graph-panel">
      <div className="panel-header">
        <div>
          <h2>Dependency graph</h2>
          <p>{positionedNodes.length} files · {edges.length} imports</p>
        </div>
        <span className="graph-icon" aria-hidden="true">
          <GitPullRequestArrow size={18} />
        </span>
      </div>

      <div className="graph-canvas" role="img" aria-label="Repository dependency graph">
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} preserveAspectRatio="xMidYMid meet">
          <g className="edge-layer">
            {edges.map((edge, index) => {
              const source = nodeMap.get(edge.source);
              const target = nodeMap.get(edge.target);

              if (!source || !target) {
                return null;
              }

              return (
                <line
                  key={`${edge.source}-${edge.target}-${index}`}
                  x1={source.x}
                  y1={source.y}
                  x2={target.x}
                  y2={target.y}
                  className="graph-edge"
                />
              );
            })}
          </g>

          <g className="node-layer">
            {positionedNodes.map((node) => {
              const isSelected = selectedNode?.id === node.id;

              return (
                <g
                  key={node.id}
                  className={`graph-node ${isSelected ? "selected" : ""}`}
                  transform={`translate(${node.x} ${node.y})`}
                  onClick={() => onSelectNode(node)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      onSelectNode(node);
                    }
                  }}
                  role="button"
                  tabIndex={0}
                  aria-label={`Select ${node.id}`}
                >
                  <circle r={isSelected ? 20 : 16} fill={nodeColor(node.group)} />
                  <text x="0" y="32" textAnchor="middle">
                    {node.label}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
    </section>
  );
}
