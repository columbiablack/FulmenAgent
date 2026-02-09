import os
import base64
import logging
from agent_network.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)

# Define the project root directory once
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

def _validate_path(user_path: str, tool_name: str) -> str:
    """
    Canonicalizes a user-provided path and checks if it falls within the project root.
    Raises ValueError if the path attempts to access outside the project root.
    """
    if not user_path:
        raise ValueError(f"{tool_name}: Path cannot be empty.")

    # 1. Resolve to an absolute path
    absolute_path = os.path.abspath(os.path.join(PROJECT_ROOT, user_path))

    # 2. Canonicalize the path to resolve '..' and '.' and symbolic links
    # This is critical for preventing path traversal
    real_path = os.path.realpath(absolute_path)

    # 3. Ensure the canonicalized path is within the project root
    if not real_path.startswith(PROJECT_ROOT):
        raise ValueError(f"{tool_name}: Attempted path traversal detected. Path '{user_path}' resolves outside project root.")
    
    return real_path

class ReadFileTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="read_file",
            description="Reads and returns the content of a specified file. Takes 'file_path' as argument."
        )

    def run(self, file_path: str):
        try:
            validated_path = _validate_path(file_path, self.name)
            with open(validated_path, 'r') as f:
                content = f.read()
            return {"status": "success", "content": content}
        except FileNotFoundError:
            return {"status": "error", "message": f"File not found: {file_path}"}
        except ValueError as ve:
            return {"status": "error", "message": str(ve)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

class WriteFileTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="write_file",
            description="Writes content to a file safely. Supports raw text or base64-encoded content. Uses atomic writes."
        )

    def run(self, file_path: str, content: str, is_base64: bool = False) -> dict:
        try:
            validated_path = _validate_path(file_path, self.name)
            
            # Ensure directory exists for the validated path
            os.makedirs(os.path.dirname(validated_path), exist_ok=True)

            # Decode base64 if requested
            if is_base64:
                try:
                    content_bytes = base64.b64decode(content)
                except Exception as e:
                    return {"status": "error", "message": f"Invalid base64 content: {e}"}
            else:
                # Assuming content is UTF-8 text if not base64
                content_bytes = content.encode("utf-8")

            # Write atomically to a temporary file first
            tmp_file = f"{validated_path}.tmp"
            with open(tmp_file, "wb") as f:
                f.write(content_bytes)

            # Replace original file
            os.replace(tmp_file, validated_path)

            return {"status": "success", "message": f"File written safely to {file_path}"}

        except ValueError as ve:
            return {"status": "error", "message": str(ve)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

class ListDirectoryTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="list_directory",
            description="Lists the contents of a specified directory. Takes 'path' as argument."
        )
        # self.project_root is now replaced by the global PROJECT_ROOT and _validate_path
        # No longer needed: self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    def run(self, path: str):
        try:
            validated_path = _validate_path(path, self.name)
            contents = os.listdir(validated_path)
            return {"status": "success", "contents": contents}
        except FileNotFoundError:
            return {"status": "error", "message": f"Directory not found: {path}"}
        except ValueError as ve:
            return {"status": "error", "message": str(ve)}
        except Exception as e:
            return {"status": "error", "message": str(e)}
