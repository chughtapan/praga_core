"""Integration test for Docker build functionality."""

import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def docker_available():
    """Check if Docker is available and skip tests if not."""
    try:
        result = subprocess.run(
            ["docker", "--version"], capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            pytest.skip("Docker not available")
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("Docker not installed or not responding")


@pytest.mark.skipif(
    os.environ.get("CI") == "true" and os.environ.get("DOCKER_AVAILABLE") != "true",
    reason="Docker not available in CI environment",
)
class TestDockerBuild:
    """Test Docker build functionality."""

    def test_dockerfile_exists(self):
        """Test that Dockerfile exists in the repository root."""
        dockerfile_path = Path("Dockerfile")
        assert dockerfile_path.exists(), "Dockerfile not found in repository root"

    def test_dockerignore_exists(self):
        """Test that .dockerignore exists in the repository root."""
        dockerignore_path = Path(".dockerignore")
        assert dockerignore_path.exists(), ".dockerignore not found in repository root"

    def test_docker_build_succeeds(self, docker_available):
        """Test that Docker build succeeds without errors."""
        # Run Docker build
        try:
            result = subprocess.run(
                ["docker", "build", "-t", "praga-mcp-test", "."],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes timeout for build
                cwd=Path.cwd(),
            )

            assert result.returncode == 0, (
                f"Docker build failed with return code {result.returncode}.\n"
                f"STDOUT: {result.stdout}\n"
                f"STDERR: {result.stderr}"
            )

            # Check that the image was created
            result = subprocess.run(
                [
                    "docker",
                    "images",
                    "--format",
                    "table {{.Repository}}:{{.Tag}}",
                    "praga-mcp-test",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            assert (
                "praga-mcp-test:latest" in result.stdout
            ), "Docker image was not created"

        except subprocess.TimeoutExpired:
            pytest.fail("Docker build timed out after 5 minutes")
        finally:
            # Clean up: remove the test image if it exists
            try:
                subprocess.run(
                    ["docker", "rmi", "praga-mcp-test"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                # Ignore cleanup errors
                pass
