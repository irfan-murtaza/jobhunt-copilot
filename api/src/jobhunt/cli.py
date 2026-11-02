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


async def _ingest_async(args: argparse.Namespace) -> None:
    import json

    from jobhunt.core.config import get_settings
    from jobhunt.core.db import dispose_engine, get_sessionmaker
    from jobhunt.core.logging import configure_logging
    from jobhunt.core.redis import close_redis, get_redis
    from jobhunt.models import JobSource
    from jobhunt.services.ingestion import IngestionService
    from jobhunt.sources.http import SourceHttpClient
    from jobhunt.sources.registry import build_sources

    settings = get_settings()
    configure_logging(settings)
    only = {JobSource(s) for s in args.source} if args.source else None
    http = SourceHttpClient(redis=None if args.no_cache else get_redis(settings))
    try:
        async with get_sessionmaker()() as session:
            report = await IngestionService(session, http).run(build_sources(settings, only))
            await session.commit()
    finally:
        await http.aclose()
        await close_redis()
        await dispose_engine()
    sys.stdout.write(json.dumps(report.as_dict(), indent=2, default=str) + "\n")


def _ingest(args: argparse.Namespace) -> None:
    asyncio.run(_ingest_async(args))


async def _extract_async(args: argparse.Namespace) -> None:
    from jobhunt.ai.factory import get_embedding_provider, get_llm_provider, model_for
    from jobhunt.ai.provider import ModelRole
    from jobhunt.core.config import get_settings
    from jobhunt.core.db import dispose_engine, get_sessionmaker
    from jobhunt.core.logging import configure_logging
    from jobhunt.models import Job
    from jobhunt.services.extraction import ExtractionService

    settings = get_settings()
    configure_logging(settings)
    total_cost = 0.0
    done = failed = 0
    async with get_sessionmaker()() as session:
        service = ExtractionService(
            session,
            get_llm_provider(),
            get_embedding_provider(),
            model=model_for(ModelRole.EXTRACT, settings),
        )
        for job_id in await service.pending_job_ids(args.limit):
            job = await session.get(Job, job_id)
            assert job is not None
            outcome = await service.extract(job)
            await session.commit()
            if outcome.error:
                failed += 1
            else:
                done += 1
                total_cost += outcome.cost_usd or 0.0
    await dispose_engine()
    sys.stdout.write(f"extracted={done} failed={failed} cost_usd={total_cost:.4f}\n")


def _extract(args: argparse.Namespace) -> None:
    asyncio.run(_extract_async(args))


async def _score_async(args: argparse.Namespace) -> None:
    from sqlalchemy import select

    from jobhunt.ai.factory import get_llm_provider, model_for
    from jobhunt.ai.provider import ModelRole
    from jobhunt.core.config import get_settings
    from jobhunt.core.db import dispose_engine, get_sessionmaker
    from jobhunt.core.logging import configure_logging
    from jobhunt.models import User
    from jobhunt.services.scoring import ScoringService

    settings = get_settings()
    configure_logging(settings)
    async with get_sessionmaker()() as session:
        user = await session.scalar(select(User).where(User.email == args.email.lower()))
        if user is None:
            sys.stderr.write(f"no user with email {args.email}\n")
            raise SystemExit(1)
        service = ScoringService(
            session, get_llm_provider(), judge_model=model_for(ModelRole.JUDGE, settings)
        )
        report = await service.score_user(user, judge_pool=args.judge_pool, rescore=args.rescore)
        await session.commit()
    await dispose_engine()
    sys.stdout.write(
        f"considered={report.considered} filtered_out={report.filtered_out} scored={report.scored} "
        f"judged={report.judged} judge_cost_usd={report.judge_cost_usd:.4f} "
        f"errors={len(report.errors)}\n"
    )


def _score(args: argparse.Namespace) -> None:
    asyncio.run(_score_async(args))


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

    ingest = sub.add_parser("ingest", help="fetch jobs from the configured sources now")
    ingest.add_argument("--source", action="append", help="limit to a source (repeatable)")
    ingest.add_argument("--no-cache", action="store_true", help="bypass the Redis response cache")
    ingest.set_defaults(func=_ingest)

    extract = sub.add_parser("extract", help="run LLM extraction on pending jobs")
    extract.add_argument("--limit", type=int, default=50)
    extract.set_defaults(func=_extract)

    score = sub.add_parser("score", help="filter, score and judge jobs for one user")
    score.add_argument("--email", required=True)
    score.add_argument("--judge-pool", type=int, default=None, help="override the judge pool size")
    score.add_argument(
        "--rescore", action="store_true", help="re-run filters and hybrid for every job"
    )
    score.set_defaults(func=_score)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
