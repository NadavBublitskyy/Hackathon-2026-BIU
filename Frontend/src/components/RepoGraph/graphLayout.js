import dagre from "dagre";

const NODE_WIDTH = 220;
const NODE_HEIGHT = 68;

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

  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir: "TB", ranksep: 56, nodesep: 32, marginx: 24, marginy: 24 });

  backendNodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });

  backendEdges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

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
      type: "smoothstep",
      markerEnd: {
        type: "arrowclosed",
        width: 16,
        height: 16,
        color: "#94a3b8",
      },
      style: {
        stroke: "#94a3b8",
        strokeWidth: 1.35,
      },
    });
  });

  const graphSize = dagreGraph.graph();

  return {
    nodes,
    edges,
    width: Math.max((graphSize?.width || 0) + 96, 960),
    height: Math.max((graphSize?.height || 0) + 96, 720),
  };
}
