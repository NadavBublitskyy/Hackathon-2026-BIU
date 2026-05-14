import os

class FileFilter:
    # Default blacklists and binary extensions
    DEFAULT_BLACKLIST_DIRS = {'.git', 'node_modules', 'venv', '__pycache__', 'dist', 'build'}
    DEFAULT_BINARY_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.pdf', '.exe', '.bin', '.pyc'}

    def __init__(self, allowed_extensions=None):
        # Allowed extensions can be customized, but default to common code file types
        self.allowed_extensions = set(allowed_extensions) if allowed_extensions else {'.py', '.js', '.java', '.cpp', '.h'}

    def is_valid(self, file_path):
        # Extract the file name and extension
        parts = file_path.split('/')
        file_name = parts[-1]
        extension = os.path.splitext(file_name)[1].lower()

        # Blacklist Filtering
        if any(part in self.DEFAULT_BLACKLIST_DIRS for part in parts):
            return False

        # Path Validation 
        if any(part.startswith('.') and part not in {'.env', '.gitignore'} for part in parts):
            return False

        # Media & Binary Exclusion
        if extension in self.DEFAULT_BINARY_EXTENSIONS:
            return False

        # Extension Validation
        if extension not in self.allowed_extensions:
            return False

        return True