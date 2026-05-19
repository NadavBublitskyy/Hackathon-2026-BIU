import { buildBackendUrl, endpoints } from "../config/endpoints";
import { requestJson } from "./apiClient";
import { normalizeRelevantContext } from "../utils/normalizers";

export const vikiService = {
  getRelevantContext: async ({ prompt, selectedFile, contextScope, repoSessionId }) => {
    const payload = await requestJson(buildBackendUrl(endpoints.vikiContext), {
      method: "POST",
      body: JSON.stringify({
        user_query: prompt,
        prompt,
        selected_file_path: selectedFile?.id || null,
        repo_session_id: repoSessionId || null,
        context_scope: contextScope || null,
      }),
    });

    return normalizeRelevantContext(payload);
  },
};
