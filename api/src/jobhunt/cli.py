"""Command-line entry point: `uv run jobhunt <command>`."""

from __future__ import annotations

import argparse
import asyncio
import sys


def _run_api(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run(
        "jobhunt.main:app", host=args.host, port=args.port, reload=args.reload, log_config=None
    )


def _run_worker(_: argparse.Namespace) -> None:
    from arq.worker import run_worker

    from jobhunt.worker.settings import WorkerSettings

    run_worker(WorkerSettings)  # type: ignore[arg-type]


def _check_config(_: argparse.Namespace) -> None:
    from jobhunt.core.config import get_settings

    settings = get_settings()
    redacted = settings.model_dump(mode="json")
    for key, value in redacted.items():
        if isinstance(value, str) and "**" in value:
            redacted[key] = "<set>"
    for key in sorted(redacted):
        sys.stdout.write(f"{key}={redacted[key]}\n")


async def _ping_redis() -> None:
    from jobhunt.core.redis import close_redis, get_redis

    sys.stdout.write(f"redis: {await get_redis().ping()}\n")
    await close_redis()


def _ping(_: argparse.Namespace) -> None:
    asyncio.run(_ping_redis())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="jobhunt")
    sub = parser.add_subparsers(dest="command", required=True)

    api = sub.add_parser("api", help="run the FastAPI server")
    api.add_argument("--host", default="0.0.0.0")  # noqa: S104 - container-friendly default
    api.add_argument("--port", type=int, default=8000)
    api.add_argument("--reload", action="store_true")
    api.set_defaults(func=_run_api)

    sub.add_parser("worker", help="run the arq background worker").set_defaults(func=_run_worker)
    sub.add_parser("config", help="print effective settings (secrets redacted)").set_defaults(
        func=_check_config
    )
    sub.add_parser("ping", help="check Redis connectivity").set_defaults(func=_ping)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
