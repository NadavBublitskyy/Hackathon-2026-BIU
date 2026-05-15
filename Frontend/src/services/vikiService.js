import { buildBackendUrl, endpoints } from "../config/endpoints";
import { requestJson } from "./apiClient";
import { normalizeRelevantContext } from "../utils/normalizers";

export const vikiService = {
  getRelevantContext: async ({ prompt, selectedFile }) => {
    const payload = await requestJson(buildBackendUrl(endpoints.vikiContext), {
      method: "POST",
      body: JSON.stringify({
        user_query: prompt,
        prompt,
        selected_file_path: selectedFile?.id || null,
        // code_chunks_json omitted — backend uses its cached copy from ingest.
      }),
    });

    return normalizeRelevantContext(payload);
  },
};
