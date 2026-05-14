import os
import re
import json

# This module defines the ProjectAnalyzer class, which takes a list of files from GitHubIngestor,
# builds a hierarchical structure, extracts imports, tags metadata, and saves the overall structure to a JSON file.
class ProjectAnalyzer:
    _LANGUAGE_MAP = {
        '.py': 'Python',
        '.js': 'JavaScript',
        '.ts': 'TypeScript',
        '.java': 'Java',
        '.cpp': 'C++',
        '.h': 'C/C++ Header',
    }
    
    # Simple heuristics to classify files based on their paths and names. This can be expanded with more keywords or patterns.
    _TYPE_RULES = [
    # Web & API
    ('Controller',       {'controller', 'controllers', 'handler', 'handlers', 'route', 'routes', 'router'}),
    ('Model',            {'model', 'models', 'entity', 'entities', 'schema', 'schemas', 'dto'}),
    ('View',             {'view', 'views', 'template', 'templates', 'component', 'components', 'ui'}),
    
    # Auth & Security
    ('Authentication',   {'auth', 'login', 'security', 'session', 'token', 'passport', 'permission', 'oauth'}),
    
    # Data & Database
    ('Database',         {'db', 'database', 'sql', 'repository', 'dao', 'store', 'persistence', 'migrations'}),
    
    # Config & Infra
    ('Configuration',    {'config', 'settings', 'env', 'properties', 'manifest', 'setup'}),
    ('Networking/API',   {'api', 'client', 'server', 'http', 'rest', 'socket', 'network', 'fetch'}),
    
    # General Logic
    ('Utility',          {'util', 'utils', 'utility', 'utilities', 'helper', 'helpers', 'common', 'lib', 'tools'}),
    ('Logic/Engine',     {'game', 'engine', 'level', 'manager', 'core', 'service', 'provider', 'action'}),
    
    # Graphics & Physics
    ('Physics/Geometry', {'collision', 'geometry', 'velocity', 'point', 'rectangle', 'line', 'math'}),
    ('UI/Graphics',      {'sprite', 'draw', 'render', 'indicator', 'canvas', 'theme', 'styles'}),
    
    # Events & Testing
    ('Listener/Event',   {'listener', 'notifier', 'event', 'handler', 'callback', 'observer'}),
    ('Testing',          {'test', 'tests', 'spec', 'mock', 'suite', 'junit'}),

    ('Logic/Engine',     {'game', 'engine', 'level', 'manager', 'core', 'remover', 'counter'}),
    ('UI/Graphics',      {'sprite', 'draw', 'render', 'indicator', 'screen', 'panel'}),
]
    def __init__(self, files):
        # files: list of {"path": str, "sha": str, ...} from GitHubIngestor
        self.files = files
        self.file_paths = {f["path"] for f in files}

    def build_hierarchy(self) -> dict:
        """Convert a flat list of file paths into a nested dictionary tree."""
        hierarchy = {}
        for file in self.files:
            parts = file["path"].split("/")
            node = hierarchy
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = {}
        return hierarchy

    def extract_imports(self, content: str, extension: str) -> list:
        """Return a list of import strings found in *content* for the given file extension."""
        if not content:
            return []

        imports = set()

        if extension == '.py':
            for pattern in (
                r'^\s*import\s+([\w\.]+)',
                r'^\s*from\s+([\w\.]+)\s+import',
            ):
                imports.update(re.findall(pattern, content, re.MULTILINE))

        elif extension in ('.js', '.ts'):
            for pattern in (
                r'import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]',
                r'import\s+[\'"]([^\'"]+)[\'"]',
                r'export\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]',
                r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
            ):
                imports.update(re.findall(pattern, content))

        elif extension == '.java':
            imports.update(re.findall(
                r'^\s*import\s+([\w\.]+(?:\.\*)?)\s*;',
                content, re.MULTILINE
            ))

        return sorted(imports)

    def tag_metadata(self, path: str) -> str:
        """Classify a file as Controller, Model, View, Utility, or Unknown."""
        lower_path = path.lower()
        parts = set(re.split(r'[/._\-]', lower_path))

        for label, keywords in self._TYPE_RULES:
            if any(keyword in lower_path for keyword in keywords):
                return label

        return 'Unknown'

    def analyze_files(self, ingestor, owner: str, repo_name: str) -> dict:
        """Fetch each file's content via *ingestor* and return per-file analysis."""
        result = {}
        for file in self.files:
            path = file["path"]
            ext = os.path.splitext(path)[1].lower()
            content = ingestor.get_file_content(owner, repo_name, file["sha"])
            imports = self.extract_imports(content, ext)
            result[path] = {
                "type": self.tag_metadata(path),
                "language": self._LANGUAGE_MAP.get(ext, "Unknown"),
                "imports": imports,
                "internal_dependencies": self._resolve_internal_dependencies(imports, ext, path),
            }
        return result

    def save_structure(
        self,
        ingestor,
        owner: str,
        repo_name: str,
        output_path: str = "structure.json",
    ) -> dict:
        """Build the full structure, save it to *output_path*, and return it."""
        structure = {
            "hierarchy": self.build_hierarchy(),
            "files": self.analyze_files(ingestor, owner, repo_name),
        }
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(structure, fh, indent=2)
        return structure


    def _resolve_internal_dependencies(self, imports: list, extension: str, file_path: str) -> list:
        """Filter *imports* down to those that resolve to a file inside the repo."""
        internal = set()

        for imp in imports:
            if extension == '.py':
                # "from utils.helper import X" -> utils/helper.py
                candidate = imp.replace('.', '/') + '.py'
                if candidate in self.file_paths:
                    internal.add(candidate)
                # Also check package __init__
                init_candidate = imp.replace('.', '/') + '/__init__.py'
                if init_candidate in self.file_paths:
                    internal.add(init_candidate)

            elif extension in ('.js', '.ts'):
                if not imp.startswith('.'):
                    continue  # third-party module
                base_dir = '/'.join(file_path.split('/')[:-1])
                normalized = self._normalize_relative_path(base_dir, imp)
                for ext in ('.js', '.ts', '.jsx', '.tsx', '.mjs'):
                    if normalized + ext in self.file_paths:
                        internal.add(normalized + ext)
                        break
                else:
                    if normalized in self.file_paths:
                        internal.add(normalized)

            elif extension == '.java':
                # "import com.example.Foo" -> com/example/Foo.java
                # Repos may place sources under src/ or src/main/java/
                base = imp.rstrip('.*')
                rel = base.replace('.', '/') + '.java'
                for candidate in (rel, 'src/' + rel, 'src/main/java/' + rel):
                    if candidate in self.file_paths:
                        internal.add(candidate)
                        break

        return sorted(internal)

    @staticmethod
    def _normalize_relative_path(base_dir: str, relative_import: str) -> str:
        """Resolve a relative import path against its base directory."""
        parts = (base_dir + '/' + relative_import).split('/')
        resolved = []
        for part in parts:
            if part == '..':
                if resolved:
                    resolved.pop()
            elif part and part != '.':
                resolved.append(part)
        return '/'.join(resolved)
