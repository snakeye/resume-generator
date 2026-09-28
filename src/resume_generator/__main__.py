"""Command-line entry point for the local repository tools."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from .config import SettingsError, load_settings
from .generation import ResumePipeline
from .github import GitHubClient, GitHubError
from .profile import ProfileError, load_profile
from .provider import ProviderError, create_provider
from .publishing import GitPublisher, PublishingError
from .runner import RunnerConfig, RunnerError, run_forced, run_forever, run_once
from .setup import SetupError, diagnose, enable_profile_git, find_root, setup_repository
from .trace import ConsoleTracer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="resume", description="Local resume generator tools")
    parser.add_argument("command", choices=("setup", "doctor", "run", "profile"), nargs="?", default="doctor")
    parser.add_argument("profile_command", choices=("validate", "enable-git"), nargs="?")
    parser.add_argument("--confirm", action="store_true", help="Confirm privacy-sensitive operations")
    parser.add_argument("--once", action="store_true", help="Process one queue cycle and exit")
    parser.add_argument("--quiet", action="store_true", help="Show only the final result and errors")
    parser.add_argument("--debug", action="store_true", help="Include technical timing details")
    parser.add_argument(
        "--force", type=int, metavar="ISSUE", help="With run, process one issue directly, ignoring its labels"
    )
    return parser


def run_profile_command(args: argparse.Namespace, *, root: Path, parser: argparse.ArgumentParser) -> int:
    if args.profile_command == "validate":
        load_profile(root / "data/profile/profile.yaml")
        print("Profile is valid: data/profile/")
        return 0
    if args.profile_command == "enable-git":
        for line in enable_profile_git(root=root, runner=subprocess.run, confirmed=args.confirm):
            print(line)
        return 0
    parser.error("profile requires the validate or enable-git subcommand")
    return 2


def run_force_command(args: argparse.Namespace, *, root: Path) -> int:
    tracer = ConsoleTracer(quiet=args.quiet, debug=args.debug)
    settings = load_settings(root)
    provider = create_provider(settings)
    github = GitHubClient(cwd=root)
    pipeline = ResumePipeline(root=root, provider=provider, on_stage=tracer.stage)
    publisher = GitPublisher(root=root, github=github)
    config = RunnerConfig(root=root)
    tracer.message("Resume runner started")
    result = run_forced(args.force, github, pipeline, config, publisher=publisher, progress=tracer.message)
    if result.success:
        tracer.result(f"Issue #{args.force} processed successfully")
        return 0
    tracer.result(f"Issue #{args.force} failed: {result.error or 'unknown error'}")
    return 1


def run_queue_command(args: argparse.Namespace, *, root: Path) -> int:
    tracer = ConsoleTracer(quiet=args.quiet, debug=args.debug)
    settings = load_settings(root)
    provider = create_provider(settings)
    github = GitHubClient(cwd=root)
    pipeline = ResumePipeline(root=root, provider=provider, on_stage=tracer.stage)
    publisher = GitPublisher(root=root, github=github)
    config = RunnerConfig(root=root)
    tracer.message("Resume runner started")
    tracer.message("Polling interval: 60s")
    if args.once:
        processed = run_once(github, pipeline, config, publisher=publisher, progress=tracer.message)
        tracer.result("Queue cycle complete: task processed" if processed else "Queue is empty")
    else:
        run_forever(github, pipeline, config, publisher=publisher, progress=tracer.message)
    return 0


def validate_force_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.command != "run":
        parser.error("--force can only be used with 'run': ./resume run --force ISSUE")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        root = find_root(Path.cwd())
        if args.command == "setup":
            for line in setup_repository(root=root, runner=subprocess.run):
                print(line)
            print("Setup complete. Edit the files in data/profile/, then run ./resume doctor.")
            return 0
        if args.command == "profile":
            return run_profile_command(args, root=root, parser=parser)
        if args.force is not None:
            validate_force_command(args, parser)
            return run_force_command(args, root=root)
        if args.command == "run":
            return run_queue_command(args, root=root)
        results = diagnose(root=root, runner=subprocess.run)
        for line in results:
            print(line)
        return 0 if all("ERROR" not in line and "MISSING" not in line for line in results) else 1
    except (GitHubError, ProfileError, ProviderError, PublishingError, SettingsError, SetupError, RunnerError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
