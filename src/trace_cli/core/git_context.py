"""Git context engine for analyzing code changes.

This module uses GitPython to:
- Find the merge base between HEAD and main/master
- Get structured diffs with file changes
- Map evidence to changed files for correlation
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()


@dataclass
class FileChange:
    """A single file change in a diff."""
    filename: str
    change_type: str  # "added", "modified", "deleted", "renamed"
    additions: int = 0
    deletions: int = 0
    old_filename: str | None = None  # For renames
    diff_content: str = ""


@dataclass
class GitDiff:
    """Structured representation of a git diff."""
    base_ref: str
    head_ref: str
    files: list[FileChange]
    total_additions: int = 0
    total_deletions: int = 0
    raw_diff: str = ""
    
    def get_changed_filenames(self) -> list[str]:
        """Get list of all changed filenames."""
        return [f.filename for f in self.files]
    
    def get_test_files(self) -> list[FileChange]:
        """Get files that look like test files."""
        test_patterns = ["test_", "_test.", ".test.", "tests/", "spec/"]
        return [
            f for f in self.files
            if any(p in f.filename.lower() for p in test_patterns)
        ]
    
    def get_source_files(self) -> list[FileChange]:
        """Get non-test source files."""
        test_files = set(f.filename for f in self.get_test_files())
        return [f for f in self.files if f.filename not in test_files]


def get_git_repo(path: Path | None = None):
    """Get a GitPython Repo object.
    
    Args:
        path: Path to the repository. Defaults to current directory.
    
    Returns:
        git.Repo object or None if not a git repository.
    """
    try:
        import git
        repo_path = path or Path.cwd()
        return git.Repo(repo_path, search_parent_directories=True)
    except ImportError:
        console.print("[red]Error:[/red] GitPython is not installed.")
        return None
    except Exception:
        return None


def find_default_branch(repo) -> str:
    """Find the default branch name (main or master).
    
    Args:
        repo: GitPython Repo object.
    
    Returns:
        Branch name ('main', 'master', or fallback).
    """
    try:
        # Try common default branch names
        for branch_name in ["main", "master", "develop"]:
            if branch_name in [ref.name for ref in repo.references]:
                return branch_name
            # Also check remote refs
            remote_ref = f"origin/{branch_name}"
            if remote_ref in [ref.name for ref in repo.references]:
                return remote_ref
        
        # Fallback: use the first branch
        if repo.heads:
            return repo.heads[0].name
        
        return "HEAD~1"  # Last resort
    except Exception:
        return "main"


def find_merge_base(repo, target_branch: str | None = None) -> str | None:
    """Find the merge base between HEAD and target branch.
    
    Args:
        repo: GitPython Repo object.
        target_branch: Target branch name. Auto-detected if None.
    
    Returns:
        Merge base commit SHA or None.
    """
    try:
        if target_branch is None:
            target_branch = find_default_branch(repo)
        
        # Get merge base
        merge_bases = repo.merge_base("HEAD", target_branch)
        if merge_bases:
            return merge_bases[0].hexsha
        
        # Fallback: use target branch directly
        return target_branch
    except Exception as e:
        console.print(f"[yellow]Warning: Could not find merge base: {e}[/yellow]")
        return None


def get_diff(
    repo=None,
    base_ref: str | None = None,
    head_ref: str = "HEAD",
    path: Path | None = None,
) -> GitDiff | None:
    """Get a structured diff between two refs.
    
    Args:
        repo: GitPython Repo object. Created if None.
        base_ref: Base reference (commit, branch). Auto-detected if None.
        head_ref: Head reference. Defaults to HEAD.
        path: Path to repository.
    
    Returns:
        GitDiff object or None on error.
    """
    if repo is None:
        repo = get_git_repo(path)
        if repo is None:
            console.print("[red]Error:[/red] Not a git repository.")
            return None
    
    try:
        # Find merge base if not provided
        if base_ref is None:
            base_ref = find_merge_base(repo)
            if base_ref is None:
                console.print("[red]Error:[/red] Could not determine base reference.")
                return None
        
        # Get the diff
        base_commit = repo.commit(base_ref)
        head_commit = repo.commit(head_ref)
        
        diffs = base_commit.diff(head_commit, create_patch=True)
        
        files: list[FileChange] = []
        total_additions = 0
        total_deletions = 0
        raw_diff_parts: list[str] = []
        
        for diff_item in diffs:
            # Determine change type
            if diff_item.new_file:
                change_type = "added"
                filename = diff_item.b_path
            elif diff_item.deleted_file:
                change_type = "deleted"
                filename = diff_item.a_path
            elif diff_item.renamed:
                change_type = "renamed"
                filename = diff_item.b_path
            else:
                change_type = "modified"
                filename = diff_item.b_path or diff_item.a_path
            
            # Get diff content
            try:
                diff_content = diff_item.diff.decode("utf-8", errors="replace") if diff_item.diff else ""
            except Exception:
                diff_content = ""
            
            # Count additions and deletions
            additions = diff_content.count("\n+") - diff_content.count("\n+++")
            deletions = diff_content.count("\n-") - diff_content.count("\n---")
            
            files.append(FileChange(
                filename=filename,
                change_type=change_type,
                additions=max(0, additions),
                deletions=max(0, deletions),
                old_filename=diff_item.a_path if diff_item.renamed else None,
                diff_content=diff_content,
            ))
            
            total_additions += max(0, additions)
            total_deletions += max(0, deletions)
            
            # Build raw diff
            if diff_content:
                raw_diff_parts.append(f"--- a/{diff_item.a_path or '/dev/null'}")
                raw_diff_parts.append(f"+++ b/{diff_item.b_path or '/dev/null'}")
                raw_diff_parts.append(diff_content)
        
        return GitDiff(
            base_ref=base_ref,
            head_ref=head_ref,
            files=files,
            total_additions=total_additions,
            total_deletions=total_deletions,
            raw_diff="\n".join(raw_diff_parts),
        )
    
    except Exception as e:
        console.print(f"[red]Error getting diff:[/red] {e}")
        return None


def get_staged_diff(path: Path | None = None) -> GitDiff | None:
    """Get diff of staged changes (for pre-commit review).
    
    Args:
        path: Path to repository.
    
    Returns:
        GitDiff object or None.
    """
    repo = get_git_repo(path)
    if repo is None:
        return None
    
    try:
        # Get staged changes
        diffs = repo.index.diff("HEAD", create_patch=True)
        
        files: list[FileChange] = []
        raw_diff_parts: list[str] = []
        
        for diff_item in diffs:
            if diff_item.new_file:
                change_type = "added"
                filename = diff_item.b_path
            elif diff_item.deleted_file:
                change_type = "deleted"
                filename = diff_item.a_path
            else:
                change_type = "modified"
                filename = diff_item.b_path or diff_item.a_path
            
            try:
                diff_content = diff_item.diff.decode("utf-8", errors="replace") if diff_item.diff else ""
            except Exception:
                diff_content = ""
            
            files.append(FileChange(
                filename=filename,
                change_type=change_type,
                diff_content=diff_content,
            ))
            
            if diff_content:
                raw_diff_parts.append(diff_content)
        
        return GitDiff(
            base_ref="HEAD",
            head_ref="INDEX",
            files=files,
            raw_diff="\n".join(raw_diff_parts),
        )
    
    except Exception as e:
        console.print(f"[red]Error getting staged diff:[/red] {e}")
        return None


def map_evidence_to_files(
    evidence_content: str,
    changed_files: list[str],
) -> dict[str, float]:
    """Map evidence content to changed files based on keyword matching.
    
    This helps prioritize which evidence is most relevant to which files.
    
    Args:
        evidence_content: The captured evidence/log content.
        changed_files: List of changed filenames.
    
    Returns:
        Dictionary mapping filename to relevance score (0.0-1.0).
    """
    relevance: dict[str, float] = {}
    evidence_lower = evidence_content.lower()
    
    for filename in changed_files:
        score = 0.0
        
        # Check for filename mentions
        basename = Path(filename).stem.lower()
        if basename in evidence_lower:
            score += 0.5
        
        # Check for path components
        parts = Path(filename).parts
        for part in parts:
            if part.lower() in evidence_lower:
                score += 0.2
        
        # Check for test file correlation
        if "test_" in filename.lower() or "_test" in filename.lower():
            # Look for test-related keywords
            test_keywords = ["pass", "fail", "error", "assert", "test"]
            for kw in test_keywords:
                if kw in evidence_lower:
                    score += 0.1
        
        relevance[filename] = min(1.0, score)
    
    return relevance
