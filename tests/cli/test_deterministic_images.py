from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_python_runtime_images_install_only_from_committed_uv_lock():
    for relative in ("ops/Dockerfile.worker", "ops/Dockerfile.channels"):
        dockerfile = (ROOT / relative).read_text()

        assert "COPY pyproject.toml uv.lock /app/" in dockerfile
        assert "uv sync --locked --no-install-project" in dockerfile or (
            "uv sync --locked --extra channels --no-install-project" in dockerfile
        )
        assert "uv sync --locked" in dockerfile
        assert "pip install" not in dockerfile
        assert "ghcr.io/astral-sh/uv:0.12.7@sha256:" in dockerfile
        assert "FROM python:3.12-slim@sha256:" in dockerfile
        assert "date -u" not in dockerfile
        assert "sha256sum" in dockerfile


def test_database_image_makes_init_scripts_world_readable_and_non_executable():
    """Require safe init SQL permissions in the database image's final stage."""
    instructions = [
        line.strip()
        for line in (ROOT / "ops/Dockerfile.db").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    copy_index = next(
        (
            index
            for index, instruction in enumerate(instructions)
            if re.fullmatch(
                r"(?i:COPY)\s+db/\*\.sql\s+/docker-entrypoint-initdb\.d/?",
                instruction,
            )
        ),
        None,
    )
    assert copy_index is not None

    chmod_pattern = re.compile(
        r"(?i:RUN)\s+chmod\s+(?P<mode>0?[0-7]{3})\s+"
        r"/docker-entrypoint-initdb\.d/\*\.sql"
    )
    chmod_instruction = next(
        (
            (index, match)
            for index, instruction in enumerate(instructions)
            if (match := chmod_pattern.fullmatch(instruction))
        ),
        None,
    )

    assert chmod_instruction is not None
    chmod_index, chmod_match = chmod_instruction
    assert copy_index < chmod_index
    assert not any(
        re.match(r"(?i:FROM)(?:\s|$)", instruction)
        for instruction in instructions[copy_index + 1 :]
    )
    assert not any(
        "/docker-entrypoint-initdb.d" in instruction
        for instruction in instructions[chmod_index + 1 :]
    )

    mode = int(chmod_match.group("mode"), 8)
    assert mode & 0o444 == 0o444
    assert mode & 0o111 == 0


def test_uv_lock_covers_runtime_and_channel_only_dependencies():
    lock = (ROOT / "uv.lock").read_text()

    assert lock.startswith("version = 1\n")
    for package in (
        "hexis",
        "pywebpush",
        "tiktoken",
        "discord-py",
        "python-telegram-bot",
        "slack-bolt",
        "matrix-nio",
    ):
        assert f'name = "{package}"' in lock


def test_source_setup_and_watch_treat_lock_as_authoritative():
    mise = (ROOT / "mise.toml").read_text()
    compose = (ROOT / "docker-compose.yml").read_text()

    assert "uv sync --locked --inexact --python 3.12" in mise
    assert "uv pip install --python .venv/bin/python -e ." not in mise
    assert "path: ./uv.lock" in compose
