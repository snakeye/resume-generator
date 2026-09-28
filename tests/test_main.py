import pytest

from resume_generator.__main__ import build_parser, main


def test_force_is_attached_to_run_command():
    args = build_parser().parse_args(["run", "--force", "6"])

    assert args.command == "run"
    assert args.force == 6


def test_force_without_run_command_is_rejected(capsys):
    with pytest.raises(SystemExit):
        main(["--force", "6"])

    assert "--force can only be used with 'run'" in capsys.readouterr().err
