import { useMemo, useState } from "react";
import { brainService } from "../services/brainService";
import { classificationService } from "../services/classificationService";
import { vikiService } from "../services/vikiService";
import { questionCategories } from "../utils/questionClassifier";

const createMessage = (role, content, metadata = {}) => ({
  id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
  role,
  content,
  metadata,
  createdAt: new Date().toISOString(),
});

export const useChatController = ({ structureJson, codeChunksJson, selectedNode }) => {
  const [messages, setMessages] = useState([]);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");

  const canAskRepoQuestions = useMemo(() => Boolean(structureJson && codeChunksJson), [structureJson, codeChunksJson]);

  const askQuestion = async (prompt) => {
    let route = null;

    setStatus("classifying");
    setError("");

    try {
      route = await classificationService.classifyPrompt({ prompt, selectedNode });
      const userMessage = createMessage("user", prompt, { route });

      setMessages((currentMessages) => [...currentMessages, userMessage]);
      setStatus("answering");

      let answer;

      if (route.category === questionCategories.GENERAL) {
        answer = await brainService.askGeneral(prompt);
      } else if (route.category === questionCategories.SPECIFIC_CODE) {
        if (!canAskRepoQuestions) {
          throw new Error("Ingest a repository before asking code-specific questions.");
        }

        const relevantContextJson = await vikiService.getRelevantContext({
          prompt,
          selectedFile: selectedNode,
          structureJson,
          codeChunksJson,
        });

        answer = await brainService.askWithContext({
          prompt,
          structureJson,
          relevantContextJson,
        });
      } else {
        if (!canAskRepoQuestions) {
          throw new Error("Ingest a repository before asking repo-wide questions.");
        }

        answer = await brainService.askWithContext({
          prompt,
          structureJson,
          relevantContextJson: codeChunksJson,
        });
      }

      const assistantMessage = createMessage("assistant", answer.response || "No answer returned.", {
        route,
        model: answer.answered_by_model || answer.selected_model,
        pathsVerified: answer.paths_verified,
        fallbackUsed: answer.fallback_used,
      });

      setMessages((currentMessages) => [...currentMessages, assistantMessage]);
      setStatus("idle");
    } catch (caughtError) {
      setError(caughtError.message || "Failed to ask the chatbot backend.");
      setStatus("error");
      setMessages((currentMessages) => [
        ...currentMessages,
        createMessage("assistant", caughtError.message || "Failed to ask the chatbot backend.", {
          route,
          isError: true,
        }),
      ]);
    }
  };

  const clearMessages = () => {
    setMessages([]);
    setStatus("idle");
    setError("");
  };

  return {
    messages,
    status,
    error,
    askQuestion,
    clearMessages,
  };
};
