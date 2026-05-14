const pathLabel = (path) => path.split("/").filter(Boolean).at(-1) || path;

const groupFromPath = (path) => {
  const parts = path.split("/").filter(Boolean);

  if (parts.length >= 2) {
    return parts.at(-2);
  }

  return "root";
};

const extractFilePath = (file) => file?.path || file?.file_path || file?.id || "";

const extractImportValue = (importItem) => {
  if (typeof importItem === "string") {
    return importItem;
  }

  return importItem?.path || importItem?.module || importItem?.name || importItem?.source || "";
};

const resolveImportTarget = (importValue, knownPaths) => {
  if (!importValue) {
    return null;
  }

  const normalized = importValue.replace(/^\.+\//, "").replace(/\./g, "/");

  return (
    knownPaths.find((path) => path === importValue) ||
    knownPaths.find((path) => path.endsWith(`${normalized}.py`)) ||
    knownPaths.find((path) => path.endsWith(normalized)) ||
    null
  );
};

export const buildGraphFromStructure = (structureJson) => {
  const files = Array.isArray(structureJson?.files) ? structureJson.files : [];
  const paths = files.map(extractFilePath).filter(Boolean);

  const nodes = paths.map((path) => {
    const file = files.find((candidate) => extractFilePath(candidate) === path) || {};

    return {
      id: path,
      label: file.name || pathLabel(path),
      group: file.group || groupFromPath(path),
      definitions: file.definitions || { classes: [], functions: [], variables: [] },
    };
  });

  const edges = files.flatMap((file) => {
    const source = extractFilePath(file);
    const imports = Array.isArray(file.imports) ? file.imports : [];

    return imports
      .map(extractImportValue)
      .map((importValue) => resolveImportTarget(importValue, paths))
      .filter((target) => target && source && target !== source)
      .map((target) => ({ source, target, type: "import" }));
  });

  return { nodes, edges };
};

export const normalizeGraphData = (payload) => {
  const graph = payload?.graph_data || payload?.graphData || payload?.graph || payload;
  const nodes = Array.isArray(graph?.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph?.edges) ? graph.edges : Array.isArray(graph?.links) ? graph.links : [];

  return { nodes, edges };
};

export const createGraphLayout = (graphData, width = 880, height = 620) => {
  const nodes = graphData.nodes || [];
  const radius = Math.min(width, height) * 0.36;
  const centerX = width / 2;
  const centerY = height / 2;
  const groups = [...new Set(nodes.map((node) => node.group || "root"))];

  return nodes.map((node, index) => {
    const groupIndex = Math.max(groups.indexOf(node.group || "root"), 0);
    const angle = (index / Math.max(nodes.length, 1)) * Math.PI * 2;
    const groupOffset = (groupIndex - groups.length / 2) * 18;

    return {
      ...node,
      x: centerX + Math.cos(angle) * (radius + groupOffset),
      y: centerY + Math.sin(angle) * (radius - groupOffset * 0.5),
    };
  });
};
