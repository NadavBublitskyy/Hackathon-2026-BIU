import io
import os
import re
import base64
import zipfile

import requests
from dotenv import load_dotenv
from github import Github, GithubException
from Ingestor.file_filter import FileFilter

load_dotenv()

class GitHubIngestor:
    def __init__(self, token=None, file_filter=None):
        self.token = token or os.getenv('GITHUB_TOKEN')
        if self.token:
            self.gh = Github(self.token)
        else:
            self.gh = Github()
        self.filter = file_filter or FileFilter()

    def parse_github_url(self, url):
        pattern = r'https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$'
        match = re.search(pattern, url)
        if not match:
            raise ValueError("Invalid GitHub URL")
        owner, repo = match.groups()
        return owner, repo

    def check_connection(self):
        try:
            if self.token:
                user = self.gh.get_user()
                return f"Authenticated as: {user.login}"
            else:
                self.gh.get_rate_limit()
                return "Connected Anonymously (Rate limited)"
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def download_repository_zip(self, url: str) -> dict:
        """Download the entire repository as a ZIP archive (single request, no token required).

        Returns the same shape as get_repository_files but each file dict also
        contains a 'content' key so ProjectAnalyzer needs no further API calls.
        """
        owner, repo_name = self.parse_github_url(url)

        # Try 'main' then 'master' to locate the default branch without an API call.
        content_bytes = None
        for branch in ('main', 'master'):
            zip_url = f"https://github.com/{owner}/{repo_name}/archive/refs/heads/{branch}.zip"
            try:
                resp = requests.get(zip_url, timeout=60, headers={"User-Agent": "Repo-Analyzer"})
                if resp.status_code == 200:
                    content_bytes = resp.content
                    break
            except requests.RequestException:
                continue

        if content_bytes is None:
            return {"error": "Could not download repository ZIP. The repository may not exist or may be private."}

        files_list = []
        try:
            with zipfile.ZipFile(io.BytesIO(content_bytes)) as zf:
                namelist = zf.namelist()
                if not namelist:
                    return {"error": "Downloaded ZIP archive is empty."}

                # GitHub names the root folder "{repo}-{branch}/". Detect it from
                # the first entry rather than constructing it, to handle repos whose
                # names contain dots or other characters GitHub normalises.
                prefix = namelist[0].split('/')[0] + '/'
                prefix_len = len(prefix)

                for name in namelist:
                    if not name.startswith(prefix):
                        continue
                    rel_path = name[prefix_len:]
                    # Skip directory entries (end with '/') and the root itself.
                    if not rel_path or rel_path.endswith('/'):
                        continue
                    if not self.filter.is_valid(rel_path):
                        continue
                    try:
                        raw = zf.read(name)
                        content = raw.decode('utf-8', errors='replace')
                    except Exception:
                        continue
                    files_list.append({
                        "path": rel_path,
                        "name": rel_path.split('/')[-1],
                        "size_bytes": len(raw),
                        "sha": None,      # not available from ZIP download
                        "content": content,
                    })
        except zipfile.BadZipFile:
            return {"error": "Downloaded file is not a valid ZIP archive."}

        return {"owner": owner, "repo": repo_name, "files": files_list}

    def get_repository_files(self, url):
        """Fetch file list via the GitHub API tree endpoint (requires a token for large repos)."""
        owner, repo_name = self.parse_github_url(url)
        try:
            repo = self.gh.get_repo(f"{owner}/{repo_name}")
            default_branch = repo.default_branch
            tree = repo.get_git_tree(sha=default_branch, recursive=True)
            files_list = []
            for item in tree.tree:
                if item.type == "blob" and self.filter.is_valid(item.path):
                    files_list.append({
                        "path": item.path,
                        "name": item.path.split('/')[-1],
                        "size_bytes": item.size,
                        "sha": item.sha,
                    })
            return {"owner": owner, "repo": repo_name, "files": files_list}
        except GithubException as e:
            if e.status == 404:
                return {"error": "Repository not found. It might be private or deleted."}
            elif e.status == 401:
                return {"error": "Invalid GitHub Token. Please check your .env file."}
            else:
                return {"error": f"GitHub API error: {e.data.get('message', str(e))}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}

    def get_file_content(self, owner, repo_name, file_sha):
        """Fetch a single file's content by SHA via the GitHub blob API."""
        try:
            repo = self.gh.get_repo(f"{owner}/{repo_name}")
            blob = repo.get_git_blob(file_sha)
            if blob.encoding == "base64":
                return base64.b64decode(blob.content).decode("utf-8", errors="replace")
            return blob.content
        except GithubException:
            return None
        except Exception:
            return None
