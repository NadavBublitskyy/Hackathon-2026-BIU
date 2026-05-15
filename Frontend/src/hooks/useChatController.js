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

      const assistantMessageId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
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

      if (route.category === questionCategories.GENERAL) {
        streamIterator = brainService.streamGeneral(prompt);
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

        streamIterator = brainService.streamWithContext({
          prompt,
          structureJson,
          relevantContextJson,
        });
      } else {
        if (!canAskRepoQuestions) {
          throw new Error("Ingest a repository before asking repo-wide questions.");
        }

        streamIterator = brainService.streamWithContext({
          prompt,
          structureJson,
          relevantContextJson: codeChunksJson,
        });
      }

      for await (const { event, data } of streamIterator) {
        if (event === "start") {
          setMessages((msgs) =>
            msgs.map((msg) =>
              msg.id === assistantMessageId
                ? {
                    ...msg,
                    metadata: {
                      ...msg.metadata,
                      model: data.selected_model || "openrouter/auto",
                      pathsVerified: data.paths_verified,
                      fallbackUsed: data.fallback_used,
                    },
                  }
                : msg
            )
          );
        } else if (event === "token") {
          setMessages((msgs) =>
            msgs.map((msg) =>
              msg.id === assistantMessageId
                ? { ...msg, content: msg.content + data.token }
                : msg
            )
          );
        } else if (event === "error") {
          throw new Error(data.detail || "Streaming error occurred.");
        } else if (event === "done") {
          break;
        }
      }

      setStatus("idle");
    } catch (caughtError) {
      setError(caughtError.message || "Failed to ask the chatbot backend.");
      setStatus("error");
      
      setMessages((currentMessages) => {
        // If the error happened during streaming, the last message is the assistant message
        const isAssistantMessageEmpty = currentMessages.length > 0 && 
                                        currentMessages[currentMessages.length - 1].role === "assistant" &&
                                        !currentMessages[currentMessages.length - 1].content;
        
        if (isAssistantMessageEmpty) {
           return currentMessages.map((msg, index) => 
             index === currentMessages.length - 1 
               ? { ...msg, content: caughtError.message || "Failed to ask the chatbot backend.", metadata: { ...msg.metadata, isError: true } }
               : msg
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
