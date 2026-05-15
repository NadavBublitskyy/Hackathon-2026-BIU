import os
from tree_sitter_languages import get_parser


class CodeChunker:
    _EXTENSION_MAP = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.java': 'java',
    }

    _CLASS_TYPES = {
        'python':     {'class_definition'},
        'javascript': {'class_declaration'},
        'typescript': {'class_declaration'},
        'java':       {'class_declaration', 'interface_declaration',
                       'enum_declaration', 'record_declaration'},
    }

    _FUNCTION_TYPES = {
        'python':     {'function_definition'},
        'javascript': {'function_declaration', 'method_definition'},
        'typescript': {'function_declaration', 'method_definition'},
        'java':       {'method_declaration', 'constructor_declaration'},
    }

    def chunk(self, content: str, file_path: str) -> list:
        ext = os.path.splitext(file_path)[1].lower()
        lang = self._EXTENSION_MAP.get(ext)
        if lang is None:
            return []

        try:
            parser = get_parser(lang)
        except Exception as e:
            print(f"[CodeChunker] Could not load parser for '{lang}': {e}")
            return []

        if not content:
            return []

        # Encode to bytes — tree-sitter always works on bytes and its byte
        # offsets (start_byte/end_byte) will be consistent with this buffer.
        content_bytes = content.encode('utf-8')

        try:
            tree = parser.parse(content_bytes)
        except Exception as e:
            print(f"[CodeChunker] Parse error for {file_path}: {e}")
            return []

        chunks: list = []
        self._walk(tree.root_node, content_bytes, file_path, lang, chunks)

        print(f"[CodeChunker] {file_path}: {len(chunks)} chunk(s) found")
        return chunks

    # ------------------------------------------------------------------

    def _get_node_name(self, node) -> str:
        """Return the entity name for a class/function node.

        Strategy (most-reliable first):
        1. Use the 'name' field exposed by the grammar (works for all
           tree-sitter-java, -python, -javascript, -typescript grammars).
        2. Linear scan of direct children for identifier-type nodes.
        3. One level deeper (handles modifiers wrapping the identifier).
        4. Fall back to 'Unnamed' so the chunk is still recorded.
        """
        # 1. Named field — the most reliable across all supported grammars.
        name_node = node.child_by_field_name('name')
        if name_node and name_node.text:
            return name_node.text.decode('utf-8')

        _IDENT_TYPES = ('identifier', 'type_identifier', 'property_identifier')

        # 2. Direct children.
        for child in node.children:
            if child.type in _IDENT_TYPES and child.text:
                return child.text.decode('utf-8')

        # 3. Grandchildren (one extra level for wrapped nodes).
        for child in node.children:
            for grandchild in child.children:
                if grandchild.type in _IDENT_TYPES and grandchild.text:
                    return grandchild.text.decode('utf-8')

        return 'Unnamed'

    def _walk(self, node, content_bytes: bytes, file_path: str, lang: str, chunks: list):
        class_types = self._CLASS_TYPES.get(lang, set())
        function_types = self._FUNCTION_TYPES.get(lang, set())

        if node.type in class_types:
            chunks.append({
                'file_path': file_path,
                'entity_name': self._get_node_name(node),
                'type': 'Class',
                'line_range': [node.start_point[0] + 1, node.end_point[0] + 1],
                'content': content_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='replace'),
            })
            # Recurse so methods inside the class are also captured.
            for child in node.children:
                self._walk(child, content_bytes, file_path, lang, chunks)

        elif node.type in function_types:
            chunks.append({
                'file_path': file_path,
                'entity_name': self._get_node_name(node),
                'type': 'Function',
                'line_range': [node.start_point[0] + 1, node.end_point[0] + 1],
                'content': content_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='replace'),
            })
            # Recurse to capture nested functions.
            for child in node.children:
                self._walk(child, content_bytes, file_path, lang, chunks)

        else:
            for child in node.children:
                self._walk(child, content_bytes, file_path, lang, chunks)
