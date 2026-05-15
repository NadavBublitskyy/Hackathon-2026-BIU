import { GitPullRequestArrow } from "lucide-react";
import { useMemo, useCallback } from "react";
import ForceGraph2D from "react-force-graph-2d";

const WIDTH = 880;
const HEIGHT = 620;

const nodeColor = (group) => {
  const palette = ["#2563eb", "#0f766e", "#b45309", "#7c3aed", "#be123c", "#15803d", "#4338ca"];
  const value = [...String(group || "root")].reduce((sum, char) => sum + char.charCodeAt(0), 0);

  return palette[value % palette.length];
};

export function RepoGraph({ graphData, selectedNode, onSelectNode }) {
  const fgData = useMemo(() => {
    return {
      nodes: graphData?.nodes || [],
      links: graphData?.edges || [],
    };
  }, [graphData]);

  const handleNodeClick = useCallback(
    (node) => {
      onSelectNode(node);
    },
    [onSelectNode]
  );

  return (
    <section className="repo-graph-panel">
      <div className="panel-header">
        <div>
          <h2>Dependency graph</h2>
          <p>{fgData.nodes.length} files · {fgData.links.length} imports</p>
        </div>
        <span className="graph-icon" aria-hidden="true">
          <GitPullRequestArrow size={18} />
        </span>
      </div>

      <div className="graph-canvas" role="region" aria-label="Repository dependency graph">
        <ForceGraph2D
          graphData={fgData}
          width={WIDTH}
          height={HEIGHT}
          nodeLabel="label"
          onNodeClick={handleNodeClick}
          linkDirectionalArrowLength={3.5}
          linkDirectionalArrowRelPos={1}
          linkColor={() => 'rgba(255, 255, 255, 0.2)'}
          nodeCanvasObject={(node, ctx, globalScale) => {
            const isSelected = selectedNode?.id === node.id;
            const radius = isSelected ? 8 : 5;
            
            ctx.beginPath();
            ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
            ctx.fillStyle = isSelected ? "#fbbf24" : nodeColor(node.group);
            ctx.fill();

            if (globalScale > 1 || isSelected) {
              const label = node.label || node.id;
              const fontSize = 12 / globalScale;
              ctx.font = `${fontSize}px Sans-Serif`;
              ctx.textAlign = 'center';
              ctx.textBaseline = 'middle';
              ctx.fillStyle = isSelected ? "#fbbf24" : 'rgba(255, 255, 255, 0.8)';
              ctx.fillText(label, node.x, node.y + radius + fontSize + 2);
            }
          }}
        />
      </div>
    </section>
  );
}
