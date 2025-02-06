import os
import re
import subprocess


def unroll_prompt_from_file(filename, dir=None):
    """
    Reads the file content from a directory specified by the
    ASSISTANTS_DIR environment variable.
    """
    base_dir = dir if dir else os.environ.get("ASSISTANTS_DIR", "")
    filepath = os.path.join(base_dir, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    return content


def get_repo_name(git_url):
    """
    Extracts the repository name from a git URL.
    For example, given "git@github.com:username/repo.git" or
    "https://github.com/username/repo.git" it returns "repo".
    """
    # Handle SSH-style URL (with colon)
    if "@" in git_url and ":" in git_url:
        part = git_url.split(":")[-1]  # e.g., "username/repo.git"
    else:
        # Handle HTTPS-style URL.
        part = git_url.rstrip("/").split("/")[-1]
    if part.endswith(".git"):
        part = part[:-4]
    return part


def unroll_prompt_from_git(git_url, file_location, branch):
    """
    Clones (or updates) a repository in a local 'repos' folder,
    then retrieves the content of a file from the specified branch.
    """
    repo_name = get_repo_name(git_url)
    repos_dir = "repos"
    repo_path = os.path.join(repos_dir, repo_name)

    # Ensure the 'repos' folder exists.
    os.makedirs(repos_dir, exist_ok=True)

    if not os.path.exists(repo_path):
        # Clone the repository if it does not exist.
        subprocess.run(["git", "clone", git_url, repo_path], check=True)
    else:
        # If it exists, fetch the latest changes.
        subprocess.run(["git", "-C", repo_path, "fetch"], check=True)

    # Use 'git show' to get the content of the file at the given branch.
    # This avoids having to checkout branches.
    result = subprocess.run(
        ["git", "-C", repo_path, "show", f"{branch}:{file_location}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def unroll_prompt(prompt, visited=None):
    """
    Recursively replaces placeholders in the prompt with their loaded content.

    There are two placeholder types:

    1. [#PLACEHOLDER_LOAD_FROM_FILE (<prompt_label>)]
       -> Loads content from a local file.

    2. [#PLACEHOLDER_LOAD_FILE_FROM_GIT (<git_url_ssh>, <file_location>, <branch>)]
       -> Clones or updates a git repository and loads content from a file in that repo.

    The visited set (of command tuples) prevents the same placeholder command
    from being processed more than once (avoiding infinite recursion).
    """
    if visited is None:
        visited = set()

    # Regular expression for file-based placeholders:
    file_pattern = re.compile(r"\[#PLACEHOLDER_LOAD_FROM_FILE\s*\(\s*([^)]+?)\s*\)\]")
    # Regular expression for git-based placeholders:
    git_pattern = re.compile(
        r"\[#PLACEHOLDER_LOAD_FILE_FROM_GIT\s*\(\s*([^,]+?)\s*,\s*([^,]+?)\s*,\s*([^)]+?)\s*\)\]"
    )

    def file_repl(match):
        filename = match.group(1).strip()
        key = ("LOAD_FROM_FILE", filename)
        if key in visited:
            # Already processed this file; avoid reprocessing.
            return match.group(0)
        visited.add(key)
        try:
            content = unroll_prompt_from_file(filename)
        except Exception as e:
            content = f"[Error loading file '{filename}': {e}]"
        # Process any placeholders within the loaded content recursively.
        return unroll_prompt(content, visited)

    def git_repl(match):
        git_url = match.group(1).strip()
        file_location = match.group(2).strip()
        branch = match.group(3).strip()
        key = ("LOAD_FROM_GIT", git_url, file_location, branch)
        if key in visited:
            return match.group(0)
        visited.add(key)
        try:
            content = unroll_prompt_from_git(git_url, file_location, branch)
        except Exception as e:
            content = (
                f"[Error loading from git ({git_url}, {file_location}, {branch}): {e}]"
            )
        # Recursively process the loaded content.
        return unroll_prompt(content, visited)

    # First, replace any file-based placeholders.
    prompt = file_pattern.sub(file_repl, prompt)
    # Then, replace any git-based placeholders.
    prompt = git_pattern.sub(git_repl, prompt)

    return prompt


# Example usage:
if __name__ == "__main__":
    # An example prompt that contains both types of placeholders.
    sample_prompt = (
        "Here is a description: [#PLACEHOLDER_LOAD_FROM_FILE (polar_bear_description.txt)]\n"
        "And here is some content from Git: [#PLACEHOLDER_LOAD_FILE_FROM_GIT (git@github.com:username/repo.git, path/to/file.txt, main)]"
    )

    # Recursively process the prompt.
    full_prompt = unroll_prompt(sample_prompt)
    print(full_prompt)
