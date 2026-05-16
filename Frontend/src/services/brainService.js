import { buildBackendUrl, endpoints } from "../config/endpoints";
import { requestJson, streamSse } from "./apiClient";
import { makeJsonFile } from "../utils/normalizers";

const buildBlueprintFormData = ({ prompt, structureJson, relevantContextJson }) => {
  const formData = new FormData();

  formData.append("prompt", prompt);
  formData.append("structure_json", makeJsonFile("structure.json", structureJson));
  formData.append("relevant_context_json", makeJsonFile("relevant_context.json", relevantContextJson));

  return formData;
};

export const brainService = {
  streamGeneral: async function* (prompt) {
    yield* streamSse(buildBackendUrl(`${endpoints.generalChat}/stream`), {
      method: "POST",
      body: JSON.stringify({ prompt }),
    });
  },

  streamWithContext: async function* ({ prompt, structureJson, relevantContextJson }) {
    yield* streamSse(buildBackendUrl(`${endpoints.blueprint}/stream`), {
      method: "POST",
      body: buildBlueprintFormData({ prompt, structureJson, relevantContextJson }),
    });
  },
};
