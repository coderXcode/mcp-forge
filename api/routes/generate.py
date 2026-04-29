"""
MCP generation routes.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from db.database import get_session
from db.models import (
    AnalysisResult, Clarification, Project, ProjectStatus, TargetLanguage
)
from core.generator.engine import GeneratorEngine
from core.generator.validator import MCPValidator
from core.versioner.snapshot import SnapshotManager

router = APIRouter(prefix="/api/projects/{project_id}/generate", tags=["generate"])


class GenerateRequest(BaseModel):
    target_language: TargetLanguage = TargetLanguage.PYTHON_FASTMCP
    label: str = ""
    description: str = ""
    auth_config: dict = {}


@router.post("/")
async def generate_mcp(
    project_id: int,
    payload: GenerateRequest,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    project = await _get_project(project_id, session)
    if project.status == ProjectStatus.GENERATING:
        raise HTTPException(409, "Generation already in progress")

    # Get analysis
    result = await session.execute(
        select(AnalysisResult)
        .where(AnalysisResult.project_id == project_id)
        .order_by(AnalysisResult.created_at.desc())
    )
    analysis = result.scalars().first()
    if not analysis:
        raise HTTPException(400, "No analysis found. Run analysis first.")

    # Extract all data from analysis BEFORE commit (avoid lazy-load in async context)
    analysis_data = {
        "language": analysis.language,
        "framework": analysis.framework,
        "base_url": "",
        "endpoints": analysis.endpoints or [],
        "schemas": analysis.schemas or {},
        "auth_info": analysis.auth_info or {},
    }

    # Fetch answered clarifications so they influence generation
    clar_result = await session.execute(
        select(Clarification)
        .where(Clarification.project_id == project_id)
        .where(Clarification.is_resolved == True)
        .order_by(Clarification.created_at.asc())
    )
    answered_clarifications = [
        {"question": c.question, "answer": c.answer}
        for c in clar_result.scalars().all()
        if c.answer
    ]

    project.status = ProjectStatus.GENERATING
    project.target_language = payload.target_language
    session.add(project)
    await session.commit()

    background.add_task(
        _run_generation,
        project_id,
        analysis_data,
        payload.target_language,
        payload.label,
        payload.description,
        payload.auth_config,
        answered_clarifications,
    )
    return {"status": "generation_started"}


@router.get("/files")
async def get_generated_files(project_id: int, session: AsyncSession = Depends(get_session)):
    project = await _get_project(project_id, session)
    sm = SnapshotManager(session)
    files = await sm.get_active_files(project)
    return {"files": files}


@router.get("/validate")
async def validate_generated(project_id: int, session: AsyncSession = Depends(get_session)):
    project = await _get_project(project_id, session)
    sm = SnapshotManager(session)
    files = await sm.get_active_files(project)
    if not files:
        raise HTTPException(404, "No generated files found")

    validator = MCPValidator()
    lang = project.target_language.value if project.target_language else "python"
    result = validator.validate(files, lang)
    return result.to_dict()


# ── Background generation ─────────────────────────────────────────────────────

async def _run_generation(
    project_id: int,
    analysis_data: dict,
    target_language: TargetLanguage,
    label: str,
    description: str,
    auth_config: dict,
    answered_clarifications: list[dict] | None = None,
):
    from db.database import AsyncSessionLocal
    from core.logger import project_log
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(select(Project).where(Project.id == project_id))
            project = result.scalars().first()
            if not project:
                return

            from config import get_settings as _gs
            _s = _gs()
            _model_label = f"{_s.llm_provider.upper()} / {_s.active_llm_model}" if _s.llm_provider != 'local' else f"local / {_s.local_model}"
            await project_log(project_id, f"Generation started — target: {target_language.value}", source="generator")
            await project_log(project_id, f"LLM: {_model_label}", source="generator")
            from core.notifier import notify as _notify, tab_link as _tl
            from db.models import NotificationType as _NT
            async with AsyncSessionLocal() as _ns:
                await _notify(_ns, project_id, _NT.INFO,
                    f"Generation started — {project.name}",
                    f"Converting to {target_language.value} using {_model_label}",
                    link=_tl(project_id, 'logs'))
                await _ns.commit()
            if _s.llm_provider == 'local':
                from core.llm.local_provider import get_status as _lm_status
                st = _lm_status()
                if st['state'] == 'not_loaded':
                    await project_log(project_id, f"Loading local model into GPU — this may take several minutes on first run...", source="generator")
                else:
                    await project_log(project_id, f"Local model already loaded ({st.get('vram_gb', '')})", source="generator")

            # Load original source files for filename preservation + verbatim copy
            source_files: dict[str, str] = {}
            if project.source_type and project.source_type.value == "local_folder" and project.source_url:
                import os
                src = project.source_url
                try:
                    for fname in os.listdir(src):
                        fpath = os.path.join(src, fname)
                        if os.path.isfile(fpath) and os.path.getsize(fpath) < 150_000:
                            try:
                                source_files[fname] = open(fpath, encoding="utf-8", errors="ignore").read()
                            except Exception:
                                pass
                except Exception:
                    pass

            engine = GeneratorEngine(
                analysis=analysis_data,
                project_name=project.name,
                target_language=target_language,
                auth_config=auth_config,
                source_files=source_files,
                clarifications=answered_clarifications or [],
            )
            files = await engine.generate()
            await project_log(project_id, f"Generated {len(files)} file(s): {', '.join(files.keys())}", source="generator")

            # Validate
            validator = MCPValidator()
            vresult = validator.validate(files, target_language.value)
            await project_log(
                project_id,
                f"Validation complete — errors: {len(vresult.errors)}, warnings: {len(vresult.warnings)}",
                level="warning" if vresult.errors else "info",
                source="validator",
            )

            # Save snapshot
            sm = SnapshotManager(session)
            snap_desc = description or (
                f"Generated for {analysis_data.get('language', '')} → {target_language.value}. "
                f"Errors: {len(vresult.errors)}, Warnings: {len(vresult.warnings)}"
            )
            await sm.create_snapshot(project, files, label=label or "auto", description=snap_desc)
            await project_log(project_id, "Snapshot saved — project status → Ready", source="generator")

            _project_name = project.name  # capture before commit expires attributes
            project.status = ProjectStatus.READY
            session.add(project)
            # Add success notification to same session
            warn_suffix = f" \u00b7 {len(vresult.errors)} error(s)" if vresult.errors else ""
            await _notify(session, project_id,
                _NT.SUCCESS if not vresult.errors else _NT.WARNING,
                f"Generation complete \u2014 {_project_name}",
                f"{len(files)} file(s) generated{warn_suffix}",
                link=_tl(project_id, 'code'))
            await session.commit()
        except Exception as e:
            await project_log(project_id, f"Generation failed: {e}", level="error", source="generator")
            result = await session.execute(select(Project).where(Project.id == project_id))
            project = result.scalars().first()
            if project:
                project.status = ProjectStatus.ERROR
                session.add(project)
                from core.notifier import notify as _notify, tab_link as _tl
                from db.models import NotificationType as _NT
                await _notify(session, project_id, _NT.ERROR,
                    "Generation failed",
                    str(e)[:200],
                    link=_tl(project_id, 'logs'))
                await session.commit()


async def _get_project(project_id: int, session: AsyncSession) -> Project:
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().first()
    if not project:
        raise HTTPException(404, "Project not found")
    return project
