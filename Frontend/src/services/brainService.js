import { buildBackendUrl, endpoints } from "../config/endpoints";
import { requestJson, streamSse } from "./apiClient";
import { makeJsonFile } from "../utils/normalizers";

const buildBlueprintFormData = ({ prompt, repoSessionId, contextScope, relevantContextJson }) => {
  const formData = new FormData();

  formData.append("prompt", prompt);
  if (repoSessionId) {
    formData.append("repo_session_id", repoSessionId);
  }
  if (contextScope) {
    formData.append("context_scope", contextScope);
  }
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

  streamWithContext: async function* ({ prompt, repoSessionId, contextScope, relevantContextJson }) {
    yield* streamSse(buildBackendUrl(`${endpoints.blueprint}/stream`), {
      method: "POST",
      body: buildBlueprintFormData({ prompt, repoSessionId, contextScope, relevantContextJson }),
    });
  },
};
