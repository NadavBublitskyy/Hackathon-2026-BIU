const FILE_PATTERN = /(?:^|\s)([\w.-]+\/)+[\w.-]+\.[a-zA-Z0-9]+/;
const CODE_SYMBOL_PATTERN = /\b(function|class|method|component|endpoint|route|handler|service|file|module|import|where is|which file|specific file)\b/i;
const REPO_WIDE_PATTERN = /\b(repo|repository|architecture|data flow|dependency|dependencies|all files|codebase|implement|feature|refactor|rewrite|debug|bug|where should|how do i add|how should i)\b/i;

export const questionCategories = {
  GENERAL: "general",
  SPECIFIC_CODE: "specific_code",
  REPO_WIDE: "repo_wide",
};

export const classifyQuestion = (prompt, selectedNode) => {
  const normalized = prompt.trim();

  if (!normalized) {
    return {
      category: questionCategories.GENERAL,
      label: "General",
      reason: "No prompt entered yet.",
    };
  }

  if (selectedNode || FILE_PATTERN.test(normalized) || CODE_SYMBOL_PATTERN.test(normalized)) {
    return {
      category: questionCategories.SPECIFIC_CODE,
      label: "Specific code",
      reason: selectedNode ? `Uses selected file ${selectedNode.id}` : "Looks like a file, symbol, or code-location question.",
    };
  }

  if (REPO_WIDE_PATTERN.test(normalized)) {
    return {
      category: questionCategories.REPO_WIDE,
      label: "Repo-wide",
      reason: "Needs repository structure and broad code context.",
    };
  }

  return {
    category: questionCategories.GENERAL,
    label: "General",
    reason: "Does not require repository context.",
  };
};
