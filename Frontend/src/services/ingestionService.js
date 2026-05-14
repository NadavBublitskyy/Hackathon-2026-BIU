import { buildBackendUrl, endpoints } from "../config/endpoints";
import { requestJson } from "./apiClient";
import { normalizeIngestResponse } from "../utils/normalizers";
import { buildGraphFromStructure, normalizeGraphData } from "../utils/graph";

export const ingestionService = {
  ingestRepo: async (githubUrl) => {
    const payload = await requestJson(buildBackendUrl(endpoints.ingest), {
      method: "POST",
      body: JSON.stringify({ github_url: githubUrl }),
    });

    const normalized = normalizeIngestResponse(payload);
    const graphData = normalized.graphData ? normalizeGraphData(normalized.graphData) : buildGraphFromStructure(normalized.structureJson);

    return {
      ...normalized,
      graphData,
    };
  },
};
