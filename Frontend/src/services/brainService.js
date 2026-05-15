import { buildBackendUrl, endpoints } from "../config/endpoints";
import { requestJson, streamSse } from "./apiClient";
import { makeJsonFile } from "../utils/normalizers";

const defaultRoutingFields = {
  light_model_name: "openrouter/auto",
  heavy_model_name: "openai/gpt-4o-mini",
  classifier_model_name: "openrouter/auto",
};

const buildBlueprintFormData = ({ prompt, structureJson, relevantContextJson }) => {
  const formData = new FormData();

  formData.append("prompt", prompt);
  formData.append("structure_json", makeJsonFile("structure.json", structureJson));
  formData.append("relevant_context_json", makeJsonFile("relevant_context.json", relevantContextJson));

  Object.entries(defaultRoutingFields).forEach(([key, value]) => {
    formData.append(key, value);
  });

  return formData;
};

export const brainService = {
  streamGeneral: async function* (prompt) {
    yield* streamSse(buildBackendUrl(`${endpoints.generalChat}/stream`), {
      method: "POST",
      body: JSON.stringify({
        prompt,
        ...defaultRoutingFields,
      }),
    });
  },

  streamWithContext: async function* ({ prompt, structureJson, relevantContextJson }) {
    yield* streamSse(buildBackendUrl(`${endpoints.blueprint}/stream`), {
      method: "POST",
      body: buildBlueprintFormData({ prompt, structureJson, relevantContextJson }),
    });
  },
};
