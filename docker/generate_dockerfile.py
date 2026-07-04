#!/usr/bin/env python3
"""Generate Dockerfile.base from template + config.toml.

Reads config.toml (SSOT) and produces:
  - Docker ENV lines for every service (from env_var field)

Usage:
    python3 docker/generate_dockerfile.py          # writes docker/Dockerfile.base
    python3 docker/generate_dockerfile.py --dry-run # prints to stdout
"""
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOML_PATH = ROOT / "config.toml"
TMPL_PATH = ROOT / "docker" / "Dockerfile.base.tmpl"
OUT_PATH = ROOT / "docker" / "Dockerfile.base"

# Shared packages that resource servers may import at runtime. Keep these out
# of config.toml because they are not standalone services.
SHARED_PACKAGES = ["auth-client"]


def parse_toml(toml_path: Path) -> dict:
    """Parse config.toml and return only mock-* environment sections."""
    cfg = tomllib.loads(toml_path.read_text())
    return {k: v for k, v in cfg.items() if k.startswith("mock-")}


def builder_block(cfg: dict) -> str:
    """Generate COPY + uv pip install for the builder stage."""
    names = sorted(cfg.keys())
    copy_lines = [
        f"COPY packages/environments/{name} /tmp/deps/{name}" for name in names
    ]
    copy_lines += [
        f"COPY packages/{name} /tmp/deps/{name}"
        for name in SHARED_PACKAGES
        if (ROOT / "packages" / name).is_dir()
    ]
    install = (
        "RUN for pkg in /tmp/deps/*/; do \\\n"
        "      uv pip install --system --no-build-isolation \"$pkg\"; \\\n"
        "    done && rm -rf /tmp/deps && \\\n"
        "    uv cache clean"
    )
    return "\n".join(copy_lines) + "\n" + install


def copy_block(cfg: dict) -> str:
    """Generate COPY --from=builder + cleanup for the final stage."""
    return (
        "COPY --from=builder /usr/local/lib/python3.12/site-packages "
        "/usr/local/lib/python3.12/site-packages\n"
        "COPY --from=builder /usr/local/bin /usr/local/bin"
    )


def env_block(cfg: dict) -> str:
    """Generate Docker ENV lines for service URLs."""
    envs: dict[str, str] = {}
    for name, svc in cfg.items():
        key = svc["env_var"]
        envs[key] = f"http://localhost:{svc['port']}"

    lines = [f"{k}={v}" for k, v in sorted(envs.items())]
    return "\n".join(f"ENV {line}" for line in lines)


def generate(dry_run: bool = False) -> str:
    cfg = parse_toml(TOML_PATH)

    tmpl = TMPL_PATH.read_text()
    result = tmpl.replace("{{MOCK_BUILDER}}", builder_block(cfg))
    result = result.replace("{{MOCK_COPY}}", copy_block(cfg))
    result = result.replace("{{MOCK_ENV}}", env_block(cfg))

    if dry_run:
        sys.stdout.write(result)
    else:
        OUT_PATH.write_text(result)
        print(f"Generated {OUT_PATH}")
        for name in sorted(cfg.keys()):
            print(f"  env: {name}")


    return result


if __name__ == "__main__":
    generate(dry_run="--dry-run" in sys.argv)
