import os
import re
import base64
from dotenv import load_dotenv
from github import Github, GithubException
from Ingestor.file_filter import FileFilter

load_dotenv()

class GitHubIngestor:
    def __init__(self, token=None, file_filter=None):
        self.token =token or os.getenv('GITHUB_TOKEN') #Get the GitHub token from the environment variable GITHUB_TOKEN if it is set
        if self.token:
            self.gh =Github(self.token) #Initialize the GitHub client with the token
        else:
            self.gh = Github() #If no token is provided, initialize the GitHub client without authentication (limited access)
        self.filter = file_filter or FileFilter()

    def parse_github_url(self, url):
        # Regular expression to match GitHub repository URLs
        pattern = r'https?://github\.com/([^/]+)/([^/]+)(?:\.git)?'
        match = re.search(pattern, url) #Extract the owner and repository name from the URL
        # If the URL does not match the expected pattern, raise an error
        if not match:
            raise ValueError("Invalid GitHub URL")
        # If the URL is valid, return the owner and repository name as a tuple
        owner, repo = match.groups()
        return owner, repo 
   
    def check_connection(self):
        # Check if the GitHub client is authenticated by trying to access the user's login information. 
        # If the token is valid, it will return the username.
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
        
    def get_repository_files(self, url):
        owner, repo_name = self.parse_github_url(url) #Parse the GitHub URL to get the owner and repository name
        try:
            repo = self.gh.get_repo(f"{owner}/{repo_name}") #Get the repository object using the GitHub client
            default_branch = repo.default_branch #Get the default branch of the repository (usually "main" or "master")
            # Get the tree of the default branch recursively to retrieve all files in the repository
            tree = repo.get_git_tree(sha=default_branch, recursive=True) 
            files_list = []
            for item in tree.tree:
                if item.type == "blob" and self.filter.is_valid(item.path):
                    files_list.append({
                        "path": item.path,
                        "name": item.path.split('/')[-1],
                        "size_bytes": item.size,
                        "sha": item.sha
                    })
            # Return a dictionary containing the owner, repository name, 
            # and a list of files with their paths, names, sizes, and SHAs
            return {
            "owner": owner,
            "repo": repo_name,
            "files": files_list
            }
        # Handle specific GitHub API exceptions to provide more informative error messages
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
        # Retrieve the content of a file from the GitHub repository using its SHA.
        try:
            repo = self.gh.get_repo(f"{owner}/{repo_name}")
            blob = repo.get_git_blob(file_sha)
            # If the blob is encoded in base64, decode it to get the original content. Otherwise, return the content as is.
            if blob.encoding == "base64":
                return base64.b64decode(blob.content).decode("utf-8", errors="replace")
            return blob.content
        except GithubException as e:
            return None
        except Exception:
            return None
