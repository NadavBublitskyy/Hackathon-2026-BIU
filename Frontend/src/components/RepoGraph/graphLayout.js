import dagre from "dagre";

const NODE_WIDTH = 190;
const NODE_HEIGHT = 58;

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
  dagreGraph.setGraph({ rankdir: "LR", ranksep: 92, nodesep: 44, marginx: 28, marginy: 28 });

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
      type: "default",
      position: {
        x: position.x - NODE_WIDTH / 2,
        y: position.y - NODE_HEIGHT / 2,
      },
      data: {
        label: node.label || node.id,
        originalNode: {
          id: node.id,
          label: node.label || node.id,
          group: node.group || "root",
        },
      },
      style: {
        width: NODE_WIDTH,
        minHeight: NODE_HEIGHT,
        borderColor: isSelected ? "#111827" : color,
        borderWidth: isSelected ? 3 : 2,
        borderRadius: 8,
        background: "#ffffff",
        boxShadow: isSelected
          ? "0 12px 24px rgba(17, 24, 39, 0.18)"
          : "0 8px 18px rgba(24, 33, 47, 0.10)",
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
      animated: edge.type === "import",
      type: "smoothstep",
      markerEnd: {
        type: "arrowclosed",
      },
      style: {
        stroke: "#8391a5",
        strokeWidth: 1.6,
      },
    });
  });

  return { nodes, edges };
}
