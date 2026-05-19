import { buildBackendUrl, endpoints } from "../config/endpoints";
import { requestJson } from "./apiClient";

export const classificationService = {
  classifyPrompt: async ({ prompt, selectedNode, repoSessionId }) => {
    return requestJson(buildBackendUrl(endpoints.promptClassify), {
      method: "POST",
      body: JSON.stringify({
        prompt,
        selected_file_path: selectedNode?.id || null,
        repo_session_id: repoSessionId || null,
      }),
    });
  },
};
