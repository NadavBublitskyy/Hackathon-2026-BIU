import { buildBackendUrl, endpoints } from "../config/endpoints";
import { requestJson } from "./apiClient";

const toClassifierContext = (retrievedContextJson = []) => {
  if (!Array.isArray(retrievedContextJson)) {
    return [];
  }

  return retrievedContextJson.map((item) => ({
    file_path: item.file_path || item.path || item.filename || "",
    function_name: item.function_name || item.name || item.entity_name || item.symbol || "",
    score: item.score,
    start_line: item.start_line || item.line_range?.[0],
    end_line: item.end_line || item.line_range?.[1],
  }));
};

export const classificationService = {
  classifyPrompt: async ({ prompt, selectedNode, retrievedContextJson }) => {
    return requestJson(buildBackendUrl(endpoints.promptClassify), {
      method: "POST",
      body: JSON.stringify({
        prompt,
        selected_file_path: selectedNode?.id || null,
        retrieved_context: toClassifierContext(retrievedContextJson),
        classifier_model_name: "openai/gpt-4o-mini",
      }),
    });
  },
};
