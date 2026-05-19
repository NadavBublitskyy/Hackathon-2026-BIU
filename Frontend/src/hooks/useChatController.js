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

export const useChatController = ({ repoSessionId, selectedNode }) => {
  const [messages, setMessages] = useState([]);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");

  const canAskRepoQuestions = useMemo(() => Boolean(repoSessionId), [repoSessionId]);

  const askQuestion = async (prompt) => {
    let route = null;
    let assistantMessageId = null;

    setStatus("classifying");
    setError("");

    try {
      route = await classificationService.classifyPrompt({ prompt, selectedNode, repoSessionId });
      const userMessage = createMessage("user", prompt, { route });
      assistantMessageId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;

      setMessages((currentMessages) => [
        ...currentMessages,
        userMessage,
        {
          id: assistantMessageId,
          role: "assistant",
          content: "",
          metadata: { route },
          createdAt: new Date().toISOString(),
        },
      ]);
      setStatus("answering");

      let streamIterator;
      let relevantContextJson = [];

      if (route.category === questionCategories.GENERAL) {
        streamIterator = brainService.streamGeneral(prompt);
      } else if (route.category === questionCategories.SPECIFIC_CODE) {
        if (!canAskRepoQuestions) {
          throw new Error("Ingest a repository before asking code-specific questions.");
        }

        relevantContextJson = await vikiService.getRelevantContext({
          prompt,
          selectedFile: selectedNode,
          contextScope: questionCategories.SPECIFIC_CODE,
          repoSessionId,
        });

        streamIterator = brainService.streamWithContext({
          prompt,
          repoSessionId,
          contextScope: questionCategories.SPECIFIC_CODE,
          relevantContextJson,
        });
      } else {
        if (!canAskRepoQuestions) {
          throw new Error("Ingest a repository before asking repo-wide questions.");
        }

        relevantContextJson = await vikiService.getRelevantContext({
          prompt,
          selectedFile: null,
          contextScope: questionCategories.REPO_WIDE,
          repoSessionId,
        });

        streamIterator = brainService.streamWithContext({
          prompt,
          repoSessionId,
          contextScope: questionCategories.REPO_WIDE,
          relevantContextJson,
        });
      }

      for await (const { event, data } of streamIterator) {
        if (event === "start") {
          setMessages((currentMessages) =>
            currentMessages.map((message) =>
              message.id === assistantMessageId
                ? {
                    ...message,
                    metadata: {
                      ...message.metadata,
                      model: data.answered_by_model || data.selected_model,
                      pathsVerified: data.paths_verified,
                      fallbackUsed: data.fallback_used,
                    },
                  }
                : message
            )
          );
        } else if (event === "token") {
          setMessages((currentMessages) =>
            currentMessages.map((message) =>
              message.id === assistantMessageId ? { ...message, content: message.content + data.token } : message
            )
          );
        } else if (event === "error") {
          throw new Error(data.detail || "Streaming error occurred.");
        } else if (event === "done") {
          break;
        }
      }

      setMessages((currentMessages) =>
        currentMessages.map((message) =>
          message.id === assistantMessageId && !message.content ? { ...message, content: "No answer returned." } : message
        )
      );
      setStatus("idle");
    } catch (caughtError) {
      setError(caughtError.message || "Failed to ask the chatbot backend.");
      setStatus("error");
      setMessages((currentMessages) => {
        if (assistantMessageId && currentMessages.some((message) => message.id === assistantMessageId)) {
          return currentMessages.map((message) =>
            message.id === assistantMessageId
              ? {
                  ...message,
                  content: message.content || caughtError.message || "Failed to ask the chatbot backend.",
                  metadata: { ...message.metadata, isError: true },
                }
              : message
          );
        }

        return [
          ...currentMessages,
          createMessage("assistant", caughtError.message || "Failed to ask the chatbot backend.", {
            route,
            isError: true,
          }),
        ];
      });
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
