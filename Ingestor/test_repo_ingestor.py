from Ingestor import repo_ingestor


class FakeGitHubIngestor:
    def get_repository_files(self, github_url):
        return {
            "owner": "owner",
            "repo": "repo",
            "files": [
                {"path": "src/main/Main.java", "name": "Main.java", "size_bytes": 98, "sha": "main-sha"},
                {"path": "src/game/Game.java", "name": "Game.java", "size_bytes": 38, "sha": "game-sha"},
                {"path": "src/geometry/Point.java", "name": "Point.java", "size_bytes": 40, "sha": "point-sha"},
            ],
        }

    def get_file_content(self, owner, repo_name, file_sha):
        return {
            "main-sha": "package main;\nimport game.Game;\nimport java.util.List;\npublic class Main {}",
            "game-sha": "package game;\npublic class Game {}",
            "point-sha": "package geometry;\npublic class Point {}",
        }[file_sha]


def test_ingest_repo_resolves_java_internal_imports_to_repo_relative_paths(monkeypatch):
    monkeypatch.setattr(repo_ingestor, "GitHubIngestor", FakeGitHubIngestor)

    result = repo_ingestor.ingest_repo("https://github.com/owner/repo")

    main_file = next(file for file in result["structure_json"]["files"] if file["path"] == "src/main/Main.java")
    assert main_file["imports"] == ["src/game/Game.java"]
    assert result["code_chunks_json"]
