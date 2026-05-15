import { buildBackendUrl, endpoints } from "../config/endpoints";
import { requestJson } from "./apiClient";

export const graphService = {
  getNodeDetails: async ({ structureJson, nodeId }) => {
    return requestJson(buildBackendUrl(endpoints.graphNodeDetails), {
      method: "POST",
      body: JSON.stringify({
        structure: structureJson,
        node_id: nodeId,
      }),
    });
  },
};
