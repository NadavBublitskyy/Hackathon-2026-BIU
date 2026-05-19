import { Send, X } from "lucide-react";
import { useState } from "react";
import { RouteBadge } from "../RouteBadge/RouteBadge";
import { questionCategories } from "../../utils/questionClassifier";

export function PromptComposer({ disabled, selectedNode, onAsk, onClearNode }) {
  const [prompt, setPrompt] = useState("");
  const route = prompt.trim() ? { category: questionCategories.PENDING, label: "LLM route" } : null;
  const canSend = prompt.trim() && !disabled;

  const submitPrompt = (event) => {
    event.preventDefault();

    if (!canSend) {
      return;
    }

    onAsk(prompt.trim());
    setPrompt("");
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submitPrompt(event);
    }
  };

  return (
    <form className="prompt-composer" onSubmit={submitPrompt}>
      {selectedNode ? (
        <div className="selected-context">
          <span>{selectedNode.id}</span>
          <button type="button" onClick={onClearNode} style={{ background: "none", padding: 0, display: "flex", alignItems: "center", color: "inherit" }}>
            <X size={14} aria-label="Clear selected file" />
          </button>
        </div>
      ) : null}

      <textarea
        value={prompt}
        onChange={(event) => setPrompt(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask where logic lives, how to add an endpoint, or a general question..."
        rows={4}
        disabled={disabled}
      />

      <div className="composer-footer">
        <RouteBadge route={route} />
        <button type="submit" disabled={!canSend}>
          <Send size={16} />
          Send
        </button>
      </div>
    </form>
  );
}
