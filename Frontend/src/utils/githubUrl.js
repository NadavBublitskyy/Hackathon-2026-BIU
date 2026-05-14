const GITHUB_REPO_PATTERN = /^https:\/\/github\.com\/([^/\s]+)\/([^/\s#?]+?)(?:\.git)?\/?$/i;

export const parseGitHubRepoUrl = (value) => {
  const trimmed = value.trim();
  const match = trimmed.match(GITHUB_REPO_PATTERN);

  if (!match) {
    return {
      isValid: false,
      error: "Enter a public GitHub repository URL like https://github.com/user/repo",
    };
  }

  return {
    isValid: true,
    owner: match[1],
    repo: match[2].replace(/\.git$/i, ""),
    normalizedUrl: `https://github.com/${match[1]}/${match[2].replace(/\.git$/i, "")}`,
  };
};

export const validatePublicGitHubRepo = async (value) => {
  const parsed = parseGitHubRepoUrl(value);

  if (!parsed.isValid) {
    return parsed;
  }

  const response = await fetch(`https://api.github.com/repos/${parsed.owner}/${parsed.repo}`, {
    headers: { Accept: "application/vnd.github+json" },
  });

  if (response.status === 404) {
    return {
      isValid: false,
      error: "GitHub could not find this repo publicly. Check the URL or repo visibility.",
    };
  }

  if (!response.ok) {
    return {
      isValid: false,
      error: "GitHub validation failed. Try again or check your network.",
    };
  }

  const repoData = await response.json();

  if (repoData.private) {
    return {
      isValid: false,
      error: "This repository is private. Public repos do not need a GitHub token or OAuth.",
    };
  }

  return {
    ...parsed,
    isValid: true,
    defaultBranch: repoData.default_branch,
    description: repoData.description || "",
    stars: repoData.stargazers_count || 0,
  };
};
