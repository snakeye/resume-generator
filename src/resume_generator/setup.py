"""Repository setup and diagnostic checks."""

from __future__ import annotations

import getpass
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .config import has_required_provider_secret, load_settings
from .github import GitHubError, RepositoryInfo, Runner, check_authentication, discover_repository, ensure_labels
from .profile import load_profile


class SetupError(RuntimeError):
    """Raised for an actionable setup or diagnostic failure."""


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def profile(self) -> Path:
        return self.root / "data/profile/profile.yaml"

    @property
    def example_profile(self) -> Path:
        return self.root / "data/examples/profile/profile.example.yaml"

    @property
    def profile_configs(self) -> tuple[tuple[Path, Path], ...]:
        example_dir = self.root / "data/examples/profile"
        profile_dir = self.root / "data/profile"
        return tuple(
            (example_dir / f"{name}.example.yaml", profile_dir / f"{name}.yaml")
            for name in ("voice", "preferences", "aliases")
        )

    @property
    def env(self) -> Path:
        return self.root / ".env"

    @property
    def gitignore(self) -> Path:
        return self.root / ".gitignore"


PROFILE_GIT_EXCEPTIONS = {
    "!data/profile/profile.yaml",
    "!data/profile/voice.yaml",
    "!data/profile/preferences.yaml",
    "!data/profile/aliases.yaml",
}


def find_root(start: Path) -> Path:
    """Find the Git checkout containing the command invocation."""
    current = start.resolve()
    for directory in (current, *current.parents):
        if (directory / ".git").exists():
            return directory
    raise SetupError("This directory is not a Git repository. Run the command inside the cloned template.")


def check_local_tools() -> list[str]:
    """Return missing required local tools, if any."""
    required = {
        "git": "Git",
        "gh": "GitHub CLI",
        "uv": "uv",
        "xelatex": "PDF toolchain (xelatex)",
        "pdftotext": "PDF text extraction tool (pdftotext)",
        "pdfinfo": "PDF metadata tool (pdfinfo)",
    }
    return [f"{label} is not installed" for command, label in required.items() if shutil.which(command) is None]


def write_profile(paths: Paths) -> bool:
    """Create local profile files once and report whether any were created."""
    if not paths.example_profile.exists():
        raise SetupError(f"Synthetic profile is missing: {paths.example_profile}")
    paths.profile.parent.mkdir(parents=True, exist_ok=True)
    created = False
    for source, destination in ((paths.example_profile, paths.profile), *paths.profile_configs):
        if destination.exists():
            continue
        if not source.exists():
            continue
        shutil.copyfile(source, destination)
        created = True
    return created


def write_env(paths: Paths, api_key: str) -> bool:
    """Write the provider secret once without replacing an existing .env."""
    if paths.env.exists():
        return False
    if not api_key.strip():
        raise SetupError("A DeepSeek API key is required. Get one from DeepSeek and rerun setup.")
    paths.env.write_text(f"DEEPSEEK_API_KEY={api_key.strip()}\n", encoding="utf-8")
    paths.env.chmod(0o600)
    return True


def repository_checks(
    *,
    root: Path,
    runner: Runner,
) -> RepositoryInfo:
    """Authenticate and verify the repository safety requirement."""
    try:
        check_authentication(cwd=root, runner=runner)
        repository = discover_repository(cwd=root, runner=runner)
    except GitHubError as error:
        raise SetupError(f"GitHub check failed: {error}") from error
    if not repository.is_private:
        raise SetupError(
            "The repository is public. Create a private repository before adding a real profile or API key."
        )
    return repository


def setup_repository(
    *,
    root: Path,
    runner: Runner,
    api_key_reader: Callable[[], str] = lambda: getpass.getpass("DeepSeek API key: "),
) -> list[str]:
    """Perform the non-destructive first-time repository setup."""
    paths = Paths(root)
    missing_tools = check_local_tools()
    if missing_tools:
        raise SetupError("Missing prerequisites: " + "; ".join(missing_tools) + ". Install them and rerun setup.")

    repository = repository_checks(root=root, runner=runner)
    created_profile = write_profile(paths)
    created_env = write_env(paths, api_key_reader()) if not paths.env.exists() else False
    try:
        ensure_labels(cwd=root, runner=runner)
    except GitHubError as error:
        raise SetupError(f"Could not create GitHub labels: {error}") from error

    result = [f"Repository: {repository.name_with_owner} (default branch: {repository.default_branch})"]
    result.append("Created data/profile/profile.yaml" if created_profile else "Profile already exists; left unchanged")
    result.append("Created .env" if created_env else ".env already exists; left unchanged")
    result.append("GitHub labels are ready")
    return result


def profile_git_enabled(root: Path) -> bool:
    """Return whether the profile has been explicitly unignored for Git."""
    gitignore = Paths(root).gitignore
    try:
        content = gitignore.read_text(encoding="utf-8")
    except OSError:
        return False
    return PROFILE_GIT_EXCEPTIONS.issubset({line.strip() for line in content.splitlines()})


def enable_profile_git(*, root: Path, runner: Runner, confirmed: bool) -> list[str]:
    """Opt into tracking the profile after private-repository verification."""
    if not confirmed:
        raise SetupError(
            "This exposes the profile to Git history. Re-run with --confirm only "
            "after verifying the repository is private."
        )

    repository_checks(root=root, runner=runner)
    paths = Paths(root)
    load_profile(paths.profile)
    try:
        content = paths.gitignore.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise SetupError(f"Git ignore file is missing: {paths.gitignore}") from error
    except OSError as error:
        raise SetupError(f"Cannot read {paths.gitignore}: {error}") from error

    if profile_git_enabled(root):
        return ["Private Git profile mode is already enabled; .gitignore left unchanged"]

    separator = "" if content.endswith("\n") else "\n"
    exceptions = "\n".join(sorted(PROFILE_GIT_EXCEPTIONS))
    try:
        paths.gitignore.write_text(f"{content}{separator}{exceptions}\n", encoding="utf-8")
    except OSError as error:
        raise SetupError(f"Cannot update {paths.gitignore}: {error}") from error
    return [
        "Verified private repository before enabling profile tracking",
        "Enabled private Git profile mode in .gitignore",
        "No files were staged or committed; review the change before using git add",
    ]


def diagnose(*, root: Path, runner: Runner) -> list[str]:
    """Return human-readable diagnostic results without raising on expected failures."""
    results = []
    missing_tools = check_local_tools()
    results.append("Local tools: OK" if not missing_tools else "Local tools: ERROR: " + "; ".join(missing_tools))
    try:
        repository = repository_checks(root=root, runner=runner)
    except SetupError as error:
        results.append(f"GitHub repository: ERROR: {error}")
    else:
        results.append(f"GitHub repository: OK ({repository.name_with_owner}, {repository.default_branch})")
    paths = Paths(root)
    results.append("Profile: OK" if paths.profile.exists() else "Profile: MISSING; run ./resume setup")
    results.append(
        "Profile storage: private Git opt-in enabled"
        if profile_git_enabled(root)
        else "Profile storage: local (ignored by Git)"
    )
    if not paths.env.exists():
        results.append(".env: MISSING; run ./resume setup")
    else:
        try:
            settings = load_settings(root)
        except RuntimeError as error:
            results.append(f"Configuration: ERROR: {error}")
        else:
            results.append(
                "Configuration: OK"
                if has_required_provider_secret(settings)
                else "Configuration: MISSING DEEPSEEK_API_KEY; run ./resume setup"
            )
    return results
