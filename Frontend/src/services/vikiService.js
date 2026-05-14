import { buildBackendUrl, endpoints } from "../config/endpoints";
import { requestJson } from "./apiClient";
import { normalizeRelevantContext } from "../utils/normalizers";

export const vikiService = {
  getRelevantContext: async ({ prompt, selectedFile, structureJson, codeChunksJson }) => {
    const payload = await requestJson(buildBackendUrl(endpoints.vikiContext), {
      method: "POST",
      body: JSON.stringify({
        user_query: prompt,
        prompt,
        selected_file_path: selectedFile?.id || null,
        structure_json: structureJson,
        code_chunks_json: codeChunksJson,
      }),
    });

    return normalizeRelevantContext(payload);
  },
};
