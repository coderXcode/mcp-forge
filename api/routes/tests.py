"""
Test generation and execution routes.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from db.database import get_session
from db.models import Project, ProjectSnapshot, TestRun, TestStatus
from core.tester.generator import TestGenerator
from core.tester.runner import TestRunner
from core.versioner.snapshot import SnapshotManager

router = APIRouter(prefix="/api/projects/{project_id}/tests", tags=["tests"])


class TestRunRequest(BaseModel):
    regenerate_tests: bool = False
    custom_test_code: str | None = None


@router.get("/runs")
async def list_test_runs(project_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(TestRun)
        .where(TestRun.project_id == project_id)
        .order_by(TestRun.created_at.desc())
    )
    runs = result.scalars().all()
    return [
        {
            "id": r.id,
            "status": r.status.value,
            "total": r.total,
            "passed": r.passed,
            "failed": r.failed,
            "skipped": r.skipped,
            "created_at": r.created_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]


@router.get("/runs/{run_id}")
async def get_test_run(
    project_id: int, run_id: int, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(TestRun)
        .where(TestRun.id == run_id)
        .where(TestRun.project_id == project_id)
    )
    run = result.scalars().first()
    if not run:
        raise HTTPException(404, "Test run not found")
    return {
        "id": run.id,
        "status": run.status.value,
        "total": run.total,
        "passed": run.passed,
        "failed": run.failed,
        "results": run.results,
        "output": run.output,
        "test_code": run.test_code,
        "created_at": run.created_at.isoformat(),
    }


@router.post("/run")
async def run_tests(
    project_id: int,
    payload: TestRunRequest,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    project = await _get_project(project_id, session)
    sm = SnapshotManager(session)
    files = await sm.get_active_files(project)
    if not files:
        raise HTTPException(400, "No generated files. Run generation first.")

    test_run = TestRun(project_id=project_id, status=TestStatus.PENDING)
    session.add(test_run)
    await session.flush()
    run_id = test_run.id
    await session.commit()

    background.add_task(
        _execute_tests,
        project_id,
        run_id,
        files,
        payload.regenerate_tests,
        payload.custom_test_code,
    )
    return {"status": "test_run_started", "run_id": run_id}


async def _load_source_files(project) -> dict[str, str]:
    """Load original source files from local folder for context in test generation."""
    result = {}
    if not project or not project.source_url or (project.source_type and project.source_type.value != "local_folder"):
        return result
    import os
    src = project.source_url
    try:
        for fname in os.listdir(src):
            if fname.endswith((".py", ".ts", ".js", ".go", ".java", ".rb")):
                fpath = os.path.join(src, fname)
                if os.path.isfile(fpath) and os.path.getsize(fpath) < 50_000:
                    result[fname] = open(fpath, encoding="utf-8", errors="ignore").read()
    except Exception:
        pass
    return result


@router.post("/generate")
async def generate_tests(project_id: int, session: AsyncSession = Depends(get_session)):
    """Generate (but don't run) test file for the active snapshot."""
    project = await _get_project(project_id, session)
    sm = SnapshotManager(session)
    files = await sm.get_active_files(project)
    if not files:
        raise HTTPException(400, "No generated files")

    server_code = next((v for k, v in files.items() if "server" in k or "main" in k), "")
    result = await session.execute(
        select(ProjectSnapshot).where(ProjectSnapshot.id == project.active_snapshot_id)
    )
    snap = result.scalars().first()

    gen = TestGenerator()
    source_files = await _load_source_files(project)
    test_code = await gen.generate_from_code(server_code, {}, project.name, source_files=source_files)
    return {"test_code": test_code}


# ── Background ────────────────────────────────────────────────────────────────

async def _execute_tests(
    project_id: int,
    run_id: int,
    files: dict,
    regenerate: bool,
    custom_code: str | None,
):
    from datetime import datetime
    from db.database import AsyncSessionLocal
    from sqlmodel import select

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(select(TestRun).where(TestRun.id == run_id))
            run = result.scalars().first()
            if not run:
                return

            run.status = TestStatus.RUNNING
            session.add(run)
            await session.commit()

            from core.logger import project_log
            await project_log(project_id, f"Test run #{run_id} started", source="tests")
            from core.notifier import notify as _notify, tab_link as _tl
            from db.models import NotificationType as _NT

            # Get or generate test code
            test_code = custom_code
            proj_result = await session.execute(select(Project).where(Project.id == project_id))
            project = proj_result.scalars().first()
            if not test_code or regenerate:
                if not regenerate:
                    # Try to reuse last successful test code from a previous run
                    from sqlalchemy import not_
                    prev = await session.execute(
                        select(TestRun)
                        .where(TestRun.project_id == project_id)
                        .where(TestRun.test_code.isnot(None))
                        .where(not_(TestRun.test_code.like("# Test generation failed%")))
                        .where(TestRun.id != run_id)
                        .order_by(TestRun.id.desc())
                    )
                    prev_run = prev.scalars().first()
                    if prev_run and prev_run.test_code:
                        test_code = prev_run.test_code
                        await project_log(project_id, "Reusing previous test code", source="tests")
                if not test_code:
                    from config import get_settings as _gs
                    _s = _gs()
                    _model_label = f"{_s.llm_provider.upper()} / {_s.active_llm_model}" if _s.llm_provider != 'local' else f"local / {_s.local_model}"
                    await project_log(project_id, f"Generating test code with LLM: {_model_label}", source="tests")
                    server_code = next((v for k, v in files.items() if "server" in k), "")
                    source_files = await _load_source_files(project)
                    gen = TestGenerator()
                    test_code = await gen.generate_from_code(server_code, {}, project.name if project else "", source_files=source_files)
                    await project_log(project_id, "Test code generated", source="tests")

            runner = TestRunner()
            source_url  = project.source_url  if project else None
            source_type = project.source_type.value if project and project.source_type else None
            test_result = await runner.run(files, test_code, source_url=source_url, source_type=source_type)

            result = await session.execute(select(TestRun).where(TestRun.id == run_id))
            run = result.scalars().first()
            if run:
                run.status = TestStatus(test_result["status"]) if test_result["status"] in TestStatus._value2member_map_ else TestStatus.ERROR
                run.total = test_result["total"]
                run.passed = test_result["passed"]
                run.failed = test_result["failed"]
                run.skipped = test_result.get("skipped", 0)
                run.results = test_result["results"]
                run.output = test_result["output"]
                run.test_code = test_code
                run.completed_at = datetime.utcnow()
                session.add(run)
                lvl = "info" if run.status == TestStatus.PASSED else "warning"
                _passed = run.passed
                _total = run.total
                _failed = run.failed
                _skipped = run.skipped
                _status_val = run.status.value
                _icon = "\u2705" if run.status == TestStatus.PASSED else "\u274c"
                await _notify(session, project_id,
                    _NT.SUCCESS if run.status == TestStatus.PASSED else _NT.WARNING,
                    f"Tests complete \u2014 {_icon} {_passed}/{_total} passed",
                    f"Run #{run_id} \u00b7 {_failed} failed, {_skipped} skipped",
                    link=_tl(project_id, 'tests'))
                await session.commit()
                await project_log(project_id, f"Test run #{run_id} complete \u2014 {_passed}/{_total} passed ({_status_val})", level=lvl, source="tests")

                # Persist test files to generated/{slug}/tests/
                if project:
                    from config import settings as _cfg
                    from pathlib import Path as _Path
                    import json as _json
                    test_out = _cfg.output_dir / project.slug / "tests"
                    test_out.mkdir(parents=True, exist_ok=True)
                    if test_code:
                        (test_out / "test_mcp_server.py").write_text(test_code, encoding="utf-8")
                    if run.output:
                        (test_out / "output.txt").write_text(run.output, encoding="utf-8")
                    report = test_result.get("report")
                    if report:
                        (test_out / "report.json").write_text(
                            _json.dumps(report, indent=2), encoding="utf-8"
                        )
        except Exception as e:
            result = await session.execute(select(TestRun).where(TestRun.id == run_id))
            run = result.scalars().first()
            if run:
                run.status = TestStatus.ERROR
                run.output = str(e)
                session.add(run)
                await session.commit()


async def _get_project(project_id: int, session: AsyncSession) -> Project:
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().first()
    if not project:
        raise HTTPException(404, "Project not found")
    return project
