export const normalizeIngestResponse = (payload) => {
  const structureJson = payload?.structure_json || payload?.structureJson || payload?.structure || payload?.files_structure;
  const codeChunksJson = payload?.code_chunks_json || payload?.codeChunksJson || payload?.code_chunks || payload?.codeChunks || payload?.chunks;
  const graphData = payload?.graph_data || payload?.graphData || payload?.graph || null;
  const repoSessionId = payload?.repo_session_id || payload?.repoSessionId || null;

  if (!repoSessionId && (!structureJson || !codeChunksJson)) {
    throw new Error("Ingest response must include repo_session_id or structure_json and code_chunks_json.");
  }

  return {
    repoSessionId,
    structureJson,
    codeChunksJson,
    graphData,
    raw: payload,
  };
};

export const normalizeRelevantContext = (payload) => {
  const source = payload?.relevant_context || payload?.relevantContext || payload?.snippets || payload?.results || payload;
  const snippets = Array.isArray(source) ? source : [];

  return snippets.map((item, index) => ({
    file_path: item.file_path || item.path || item.filename || "",
    function_name: item.function_name || item.name || item.symbol || `snippet_${index + 1}`,
    content: item.content || item.code || item.text || "",
    score: item.score,
    start_line: item.start_line,
    end_line: item.end_line,
  }));
};

export const makeJsonFile = (name, value) => {
  return new File([JSON.stringify(value, null, 2)], name, { type: "application/json" });
};
