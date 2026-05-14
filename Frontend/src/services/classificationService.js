import { buildBackendUrl, endpoints } from "../config/endpoints";
import { requestJson } from "./apiClient";

export const classificationService = {
  classifyPrompt: async ({ prompt, selectedNode }) => {
    return requestJson(buildBackendUrl(endpoints.promptClassify), {
      method: "POST",
      body: JSON.stringify({
        prompt,
        selected_file_path: selectedNode?.id || null,
        classifier_model_name: "openai/gpt-4o-mini",
      }),
    });
  },
};
