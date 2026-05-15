const brainBaseUrl = import.meta.env.VITE_BRAIN_BASE_URL || "http://localhost:8000";

const normalizeBaseUrl = (baseUrl) => baseUrl.replace(/\/$/, "");

export const endpoints = {
  brainBaseUrl: normalizeBaseUrl(brainBaseUrl),
  ingest: import.meta.env.VITE_INGEST_ENDPOINT || "/api/ingest",
  graphNodeDetails: import.meta.env.VITE_GRAPH_NODE_DETAILS_ENDPOINT || "/api/graph/node-details",
  generalChat: import.meta.env.VITE_GENERAL_CHAT_ENDPOINT || "/api/chat/routed",
  blueprint: import.meta.env.VITE_BLUEPRINT_ENDPOINT || "/api/blueprint/routed",
  vikiContext: import.meta.env.VITE_VIKI_CONTEXT_ENDPOINT || "/api/memory/retrieve",
  promptClassify: import.meta.env.VITE_PROMPT_CLASSIFY_ENDPOINT || "/api/prompt/classify",
};

export const buildBackendUrl = (path) => {
  if (/^https?:\/\//i.test(path)) {
    return path;
  }

  return `${endpoints.brainBaseUrl}${path.startsWith("/") ? path : `/${path}`}`;
};
