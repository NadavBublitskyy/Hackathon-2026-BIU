import { buildBackendUrl, endpoints } from "../config/endpoints";
import { requestJson } from "./apiClient";

export const graphService = {
  getNodeDetails: async ({ repoSessionId, nodeId }) => {
    return requestJson(buildBackendUrl(endpoints.graphNodeDetails), {
      method: "POST",
      body: JSON.stringify({
        repo_session_id: repoSessionId,
        node_id: nodeId,
      }),
    });
  },
};
