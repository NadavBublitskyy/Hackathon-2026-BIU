import dagre from "dagre";

const NODE_WIDTH = 184;
const NODE_HEIGHT = 56;
const LAYOUT_OPTIONS = {
  ranksep: 30,
  nodesep: 14,
  edgesep: 6,
  marginx: 12,
  marginy: 12,
};

const groupColor = (group) => {
  const palette = ["#2563eb", "#0f766e", "#b45309", "#7c3aed", "#be123c", "#15803d", "#4338ca"];
  const value = [...String(group || "root")].reduce((sum, char) => sum + char.charCodeAt(0), 0);

  return palette[value % palette.length];
};

const toSafeArray = (value) => (Array.isArray(value) ? value : []);

export function createReactFlowLayout(graphData, selectedNodeId) {
  const backendNodes = [];
  const seenNodes = new Set();

  toSafeArray(graphData?.nodes).forEach((node) => {
    if (!node?.id || seenNodes.has(node.id)) {
      return;
    }

    seenNodes.add(node.id);
    backendNodes.push(node);
  });

  const nodeIds = new Set(backendNodes.map((node) => node.id));
  const backendEdges = toSafeArray(graphData?.edges).filter(
    (edge) => edge?.source && edge?.target && nodeIds.has(edge.source) && nodeIds.has(edge.target),
  );

  const dagreGraph = chooseCompactLayout(backendNodes, backendEdges);

  const nodes = backendNodes.map((node) => {
    const position = dagreGraph.node(node.id) || { x: 0, y: 0 };
    const color = groupColor(node.group);
    const isSelected = selectedNodeId === node.id;

    return {
      id: node.id,
      type: "fileNode",
      position: {
        x: position.x - NODE_WIDTH / 2,
        y: position.y - NODE_HEIGHT / 2,
      },
      data: {
        label: node.label || node.id,
        fullLabel: node.id,
        group: node.group || "root",
        color,
        isSelected,
        originalNode: {
          id: node.id,
          label: node.label || node.id,
          group: node.group || "root",
        },
      },
      style: {
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        borderColor: isSelected ? "#111827" : color,
        borderWidth: isSelected ? 3 : 2,
        borderRadius: 8,
        background: isSelected ? "#f8fafc" : "#ffffff",
        boxShadow: isSelected
          ? "0 14px 30px rgba(17, 24, 39, 0.20)"
          : "0 6px 14px rgba(24, 33, 47, 0.08)",
        color: "#18212f",
      },
    };
  });

  const seenEdges = new Set();
  const edges = [];

  backendEdges.forEach((edge, index) => {
    const id = `${edge.source}->${edge.target}`;
    if (seenEdges.has(id)) {
      return;
    }

    seenEdges.add(id);
    edges.push({
      id: edge.id || `${id}-${index}`,
      source: edge.source,
      target: edge.target,
      animated: false,
      type: "default",
      markerEnd: {
        type: "arrowclosed",
        width: 14,
        height: 14,
        color: "#a8b3c2",
      },
      style: {
        stroke: "#a8b3c2",
        strokeWidth: 1.15,
      },
    });
  });

  const graphSize = dagreGraph.graph();

  return {
    nodes,
    edges,
    width: Math.max((graphSize?.width || 0) + 36, 720),
    height: Math.max((graphSize?.height || 0) + 36, 560),
  };
}

function chooseCompactLayout(nodes, edges) {
  const layouts = ["TB", "LR"].map((direction) => buildDagreLayout(nodes, edges, direction));

  return layouts.reduce((best, candidate) => (scoreLayout(candidate, edges) < scoreLayout(best, edges) ? candidate : best));
}

function buildDagreLayout(nodes, edges, rankdir) {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir, ...LAYOUT_OPTIONS });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target, { weight: 2 });
  });

  dagre.layout(dagreGraph);

  return dagreGraph;
}

function scoreLayout(dagreGraph, edges) {
  const graphSize = dagreGraph.graph() || {};
  const area = (graphSize.width || 0) * (graphSize.height || 0);
  const aspectPenalty = Math.abs(Math.log(Math.max((graphSize.width || 1) / (graphSize.height || 1), 0.01))) * 2400;
  const edgeLength = edges.reduce((sum, edge) => {
    const source = dagreGraph.node(edge.source);
    const target = dagreGraph.node(edge.target);

    if (!source || !target) {
      return sum;
    }

    return sum + Math.abs(source.x - target.x) + Math.abs(source.y - target.y);
  }, 0);

  return area * 0.025 + edgeLength + aspectPenalty;
}
