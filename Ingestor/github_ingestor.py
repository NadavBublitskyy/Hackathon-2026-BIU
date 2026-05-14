import os #To access environment variables (where the secret token is stored)
import re
from dotenv import load_dotenv #To load environment variables from a .env file
from github import Github , GithubException #To interact with the GitHub API and handle exceptions
from file_filter import FileFilter #To filter out unwanted files based on the criteria defined in the FileFilter class

load_dotenv()

class GitHubIngestor:
    def __init__(self, token=None, file_filter=None):
        self.token =token or os.getenv('GITHUB_TOKEN') #Get the GitHub token from the environment variable GITHUB_TOKEN. This token is required to authenticate with the GitHub API. If the token is not set, raise a ValueError to inform the user that they need to set the GITHUB_TOKEN in their environment variables.
        if not self.token:
            raise ValueError("GitHub token not found. Please provide a token or set GITHUB_TOKEN in .env")
        self.gh =Github(self.token) #Initialize the GitHub client with the token
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
        try:
            user = self.gh.get_user() #Try to get the authenticated user's information to check if the connection is successful 
            return user.login #If successful, return the user's login name
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