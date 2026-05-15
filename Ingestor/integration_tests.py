from github_ingestor import GitHubIngestor
from project_analyzer import ProjectAnalyzer

def test_everything():
    ingestor = GitHubIngestor()
    test_url = "https://github.com/YaelDoron/Arkanoid-BIU-OOP-"

    print("--- Testing Ingestor (ZIP download) ---")
    repo_data = ingestor.download_repository_zip(test_url)
    if "error" in repo_data:
        print(f"Failed: {repo_data['error']}")
        return

    print(f"Found {len(repo_data['files'])} files after filtering.")

    print("\n--- Testing Analyzer ---")
    analyzer = ProjectAnalyzer(repo_data['files'])

    hierarchy = analyzer.build_hierarchy()
    print(f"Hierarchy depth: {len(hierarchy.keys())} root elements.")

    print("\n--- Generating structure.json ---")
    # No ingestor needed — content was already loaded from the ZIP.
    analyzer.save_structure(output_path="structure.json")

    print("\nAll tests passed! Check structure.json for results.")

if __name__ == "__main__":
    test_everything()
