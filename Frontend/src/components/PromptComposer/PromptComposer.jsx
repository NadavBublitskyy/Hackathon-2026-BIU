import { Send, X } from "lucide-react";
import { useMemo, useState } from "react";
import { RouteBadge } from "../RouteBadge/RouteBadge";
import { classifyQuestion } from "../../utils/questionClassifier";

export function PromptComposer({ disabled, selectedNode, onAsk }) {
  const [prompt, setPrompt] = useState("");
  const route = useMemo(() => classifyQuestion(prompt, selectedNode), [prompt, selectedNode]);
  const canSend = prompt.trim() && !disabled;

  const submitPrompt = (event) => {
    event.preventDefault();

    if (!canSend) {
      return;
    }

    onAsk(prompt.trim());
    setPrompt("");
  };

  return (
    <form className="prompt-composer" onSubmit={submitPrompt}>
      {selectedNode ? (
        <div className="selected-context">
          <span>{selectedNode.id}</span>
          <X size={14} aria-hidden="true" />
        </div>
      ) : null}

      <textarea
        value={prompt}
        onChange={(event) => setPrompt(event.target.value)}
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
