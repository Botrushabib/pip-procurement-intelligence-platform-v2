import os

import pytest


@pytest.mark.skipif(
    os.getenv("PIP_SKIP_POSTGRES_CHECK") == "1",
    reason="Postgres health validation is disabled",
)
def test_postgres_container_is_reachable():
    import subprocess

    result = subprocess.run(
        ["docker", "compose", "ps", "db"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "healthy" in result.stdout or "running" in result.stdout
