from github_ingestor import GitHubIngestor
from project_analyzer import ProjectAnalyzer

def test_everything():
    ingestor = GitHubIngestor()
    test_url = "https://github.com/YaelDoron/Arkanoid-BIU-OOP-" 
    
    print("--- Testing Ingestor ---")
    repo_data = ingestor.get_repository_files(test_url)
    if "error" in repo_data:
        print(f"Failed: {repo_data['error']}")
        return

    print(f"Found {len(repo_data['files'])} files after filtering.")

    print("\n--- Testing Analyzer ---")
    analyzer = ProjectAnalyzer(repo_data['files'])
    
    hierarchy = analyzer.build_hierarchy()
    print(f"Hierarchy depth: {len(hierarchy.keys())} root elements.")

    print("\n--- Generating structure.json ---")
    analyzer.save_structure(ingestor, repo_data['owner'], repo_data['repo'])
    
    print("\n✅ All tests passed! Check structure.json for results.")

if __name__ == "__main__":
    test_everything()