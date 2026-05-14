import { ArrowRight, Github, ShieldCheck } from "lucide-react";
import { parseGitHubRepoUrl } from "../../utils/githubUrl";

export function RepoUrlForm({ repoUrl, status, error, onRepoUrlChange, onSubmit }) {
  const parsed = parseGitHubRepoUrl(repoUrl);
  const canSubmit = parsed.isValid && status !== "validating" && status !== "ingesting";

  const handleSubmit = (event) => {
    event.preventDefault();

    if (canSubmit) {
      onSubmit(repoUrl);
    }
  };

  return (
    <form className="repo-url-form" onSubmit={handleSubmit}>
      <div className="repo-form-heading">
        <span className="repo-form-icon" aria-hidden="true">
          <Github size={26} />
        </span>
        <div>
          <h2>Connect a public GitHub repo</h2>
          <p>Paste a repository URL to generate the code map and semantic chunks.</p>
        </div>
      </div>

      <label className="repo-input-label" htmlFor="repo-url">
        GitHub repository URL
      </label>
      <div className="repo-input-row">
        <input
          id="repo-url"
          type="url"
          value={repoUrl}
          onChange={(event) => onRepoUrlChange(event.target.value)}
          placeholder="https://github.com/user/repo"
          autoFocus
        />
        <button type="submit" disabled={!canSubmit}>
          <span>Index</span>
          <ArrowRight size={18} />
        </button>
      </div>

      <div className="repo-form-footer">
        <span className={parsed.isValid ? "validation-message valid" : "validation-message"}>
          <ShieldCheck size={16} />
          {repoUrl.trim() ? (parsed.isValid ? "URL shape is valid. Public repo visibility is checked next." : parsed.error) : "Public repositories do not need a GitHub token."}
        </span>
      </div>

      {error ? <div className="form-error">{error}</div> : null}
    </form>
  );
}
