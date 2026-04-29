"""
Project CRUD + analysis trigger routes.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from db.database import get_session
from db.models import (
    AnalysisResult, Project, ProjectCreate, ProjectRead,
    ProjectSnapshot, ProjectStatus, SourceType, TargetLanguage
)
from core.analyzer.openapi import OpenAPIAnalyzer
from core.analyzer.ast_analyzer import ASTAnalyzer
from core.analyzer.endpoint_prober import EndpointProber
from core.analyzer.github_fetcher import GitHubFetcher
from slugify import slugify

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("/", response_model=list[ProjectRead])
async def list_projects(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Project).order_by(Project.created_at.desc()))
    return result.scalars().all()


@router.post("/", response_model=ProjectRead)
async def create_project(
    payload: ProjectCreate,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    slug = slugify(payload.name)
    # Ensure unique slug (check first; also handle race via suffix on IntegrityError)
    existing = await session.execute(select(Project).where(Project.slug == slug))
    if existing.scalars().first():
        slug = f"{slug}-{int(datetime.utcnow().timestamp())}"

    from sqlalchemy.exc import IntegrityError
    project = Project(**payload.model_dump(), slug=slug, status=ProjectStatus.PENDING)
    session.add(project)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        slug = f"{slug}-{int(datetime.utcnow().timestamp())}"
        project = Project(**payload.model_dump(), slug=slug, status=ProjectStatus.PENDING)
        session.add(project)
        await session.commit()
    await session.refresh(project)

    # Auto-start analysis if source URL provided
    if payload.source_url:
        project.status = ProjectStatus.ANALYZING
        session.add(project)
        await session.commit()
        # Refresh after second commit so response serialization doesn't trigger lazy loads
        await session.refresh(project)
        background.add_task(_run_analysis, project.id, payload.source_url, payload.source_type)

    return project


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: int, session: AsyncSession = Depends(get_session)):
    project = await _get_or_404(project_id, session)
    return project


@router.delete("/{project_id}")
async def delete_project(project_id: int, session: AsyncSession = Depends(get_session)):
    project = await _get_or_404(project_id, session)
    await session.delete(project)
    return {"ok": True}


@router.post("/{project_id}/analyze")
async def trigger_analysis(
    project_id: int,
    background: BackgroundTasks,
    source_url: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    project = await _get_or_404(project_id, session)
    url = source_url or project.source_url
    if not url:
        raise HTTPException(400, "No source URL provided")

    project.status = ProjectStatus.ANALYZING
    session.add(project)
    await session.commit()

    background.add_task(_run_analysis, project_id, url, project.source_type)
    return {"status": "analysis_started"}


@router.post("/{project_id}/analyze/upload")
async def analyze_upload(
    project_id: int,
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_session),
):
    """Upload code files for LLM-based analysis."""
    project = await _get_or_404(project_id, session)
    project.status = ProjectStatus.ANALYZING
    session.add(project)

    file_contents: dict[str, str] = {}
    for f in files:
        content = (await f.read()).decode("utf-8", errors="replace")
        file_contents[f.filename] = content

    background.add_task(_run_upload_analysis, project_id, file_contents)
    return {"status": "analysis_started", "files": list(file_contents.keys())}


@router.get("/{project_id}/analysis")
async def get_analysis(project_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(AnalysisResult)
        .where(AnalysisResult.project_id == project_id)
        .order_by(AnalysisResult.created_at.desc())
    )
    analysis = result.scalars().first()
    if not analysis:
        raise HTTPException(404, "No analysis found")
    return {
        "language": analysis.language,
        "framework": analysis.framework,
        "endpoints": analysis.endpoints,
        "auth_info": analysis.auth_info,
        "schemas": analysis.schemas,
    }


# ── Background tasks ──────────────────────────────────────────────────────────

async def _run_analysis(project_id: int, source_url: str, source_type: SourceType):
    """Run analysis in background, update project status."""
    from db.database import AsyncSessionLocal
    from core.logger import project_log

    error: Exception | None = None

    # ── Main analysis — scoped session closes completely before error handling ──
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Project).where(Project.id == project_id))
            project = result.scalars().first()
            if not project:
                return

            from config import get_settings as _gs
            _s = _gs()
            _model_label = f"{_s.llm_provider.upper()} / {_s.active_llm_model}" if _s.llm_provider != 'local' else f"local / {_s.local_model}"
            await project_log(project_id, f"Analysis started — source: {source_type.value}", source="analyzer")
            await project_log(project_id, f"LLM: {_model_label}", source="analyzer")

            # Choose analyzer
            if source_type == SourceType.GITHUB:
                await project_log(project_id, f"Fetching GitHub repo: {source_url}", source="analyzer")
                fetcher = GitHubFetcher(source_url)
                data = await fetcher.fetch()
                await project_log(project_id, f"Fetched {len(data.get('files', {}))} files from GitHub", source="analyzer")
                analyzer = ASTAnalyzer(data["files"])
                analysis_data = await analyzer.analyze()
                analysis_data.setdefault("docs", data.get("docs", {}))
            elif source_type == SourceType.LOCAL_FOLDER:
                await project_log(project_id, f"Reading local folder: {source_url}", source="analyzer")
                files = await _read_local_folder(source_url)
                await project_log(project_id, f"Read {len(files)} files", source="analyzer")
                # Save/update original source as v0 snapshot for diff baseline
                existing_v0_r = await session.execute(
                    select(ProjectSnapshot)
                    .where(ProjectSnapshot.project_id == project_id)
                    .where(ProjectSnapshot.version == 0)
                )
                existing_v0 = existing_v0_r.scalars().first()
                if existing_v0:
                    existing_v0.files = files
                    session.add(existing_v0)
                else:
                    src_snap = ProjectSnapshot(
                        project_id=project_id,
                        version=0,
                        label="source",
                        description="Original source files before MCP conversion",
                        files=files,
                        diff={},
                        is_active=False,
                    )
                    session.add(src_snap)
                await session.flush()
                analyzer = ASTAnalyzer(files)
                analysis_data = await analyzer.analyze()
            elif source_type == SourceType.URL:
                await project_log(project_id, f"Probing URL: {source_url}", source="analyzer")
                prober = EndpointProber(source_url)
                probe = await prober.probe()
                if probe.get("spec_content"):
                    oa = OpenAPIAnalyzer(probe["spec_content"])
                    analysis_data = await oa.analyze()
                    analysis_data["base_url"] = analysis_data.get("base_url") or source_url
                else:
                    analysis_data = {"base_url": source_url, "endpoints": probe.get("probed_endpoints", []), "language": "unknown", "framework": "unknown", "auth_info": {}, "schemas": {}}
            else:
                oa = OpenAPIAnalyzer(source_url)
                analysis_data = await oa.analyze()

            endpoint_count = len(analysis_data.get("endpoints", []))
            await project_log(project_id, f"Analysis complete — {endpoint_count} endpoints detected, language: {analysis_data.get('language', 'unknown')}, framework: {analysis_data.get('framework', 'unknown')}", source="analyzer")

            from core.notifier import notify, tab_link
            from db.models import NotificationType
            ar = AnalysisResult(
                project_id=project_id,
                language=analysis_data.get("language", ""),
                framework=analysis_data.get("framework", ""),
                endpoints=analysis_data.get("endpoints", []),
                schemas=analysis_data.get("schemas", {}),
                auth_info=analysis_data.get("auth_info", {}),
            )
            session.add(ar)
            project.status = ProjectStatus.READY
            project.analysis_result_id = ar.id
            session.add(project)
            _project_name = project.name  # capture before commit expires attributes
            await session.commit()
            await project_log(project_id, "Project status → Ready", source="analyzer")
            # Notify: analysis complete
            async with AsyncSessionLocal() as notif_session:
                await notify(
                    notif_session, project_id,
                    NotificationType.SUCCESS,
                    f"Analysis complete — {_project_name}",
                    f"{endpoint_count} endpoint(s) detected · {analysis_data.get('language','?')} / {analysis_data.get('framework','?')}",
                    link=tab_link(project_id, 'overview'),
                )
                await notif_session.commit()
    except Exception as e:
        import traceback
        print(f"[ERROR] _run_analysis project={project_id}: {e}\n{traceback.format_exc()}")
        error = e

    # ── Error handling — runs after outer session is fully closed ──────────────
    if error is not None:
        await project_log(project_id, f"Analysis failed: {error}", level="error", source="analyzer")
        try:
            async with AsyncSessionLocal() as err_session:
                res2 = await err_session.execute(select(Project).where(Project.id == project_id))
                proj2 = res2.scalars().first()
                if proj2:
                    proj2.status = ProjectStatus.ERROR
                    err_session.add(proj2)
                    from core.notifier import notify, tab_link
                    from db.models import NotificationType
                    await notify(
                        err_session, project_id,
                        NotificationType.ERROR,
                        f"Analysis failed — {proj2.name}",
                        str(error)[:200],
                        link=tab_link(project_id, 'logs'),
                    )
                    await err_session.commit()
                    print(f"[INFO] Project {project_id} status → ERROR")
        except Exception as e2:
            print(f"[ERROR] Could not set ERROR status for project {project_id}: {e2}")


async def _run_upload_analysis(project_id: int, files: dict[str, str]):
    from db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(select(Project).where(Project.id == project_id))
            project = result.scalars().first()
            if not project:
                return
            analyzer = ASTAnalyzer(files)
            analysis_data = await analyzer.analyze()
            ar = AnalysisResult(
                project_id=project_id,
                language=analysis_data.get("language", ""),
                framework=analysis_data.get("framework", ""),
                endpoints=analysis_data.get("endpoints", []),
                schemas=analysis_data.get("schemas", {}),
                auth_info=analysis_data.get("auth_info", {}),
            )
            session.add(ar)
            project.status = ProjectStatus.READY
            project.analysis_result_id = ar.id
            session.add(project)
            await session.commit()
        except Exception as e:
            try:
                await session.rollback()
            except Exception:
                pass
            try:
                async with AsyncSessionLocal() as err_session:
                    res2 = await err_session.execute(select(Project).where(Project.id == project_id))
                    proj2 = res2.scalars().first()
                    if proj2:
                        proj2.status = ProjectStatus.ERROR
                        err_session.add(proj2)
                        await err_session.commit()
            except Exception as e2:
                print(f"[ERROR] Failed to set ERROR status (upload analysis) for project {project_id}: {e2}")


async def _read_local_folder(folder_path: str) -> dict[str, str]:
    """Read all readable text files from a local folder path (server-side)."""
    import os
    from pathlib import Path

    root = Path(folder_path)
    if not root.exists():
        raise FileNotFoundError(f"Folder not found: {folder_path}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {folder_path}")

    SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
                 "dist", "build", ".next", "target", "vendor"}
    SKIP_EXTS = {".pyc", ".pyo", ".so", ".dll", ".exe", ".bin",
                 ".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico",
                 ".zip", ".tar", ".gz", ".lock", ".sum"}
    MAX_FILE_SIZE = 150_000  # 150 KB per file
    MAX_FILES = 200

    files: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip dirs in-place
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            if len(files) >= MAX_FILES:
                break
            fp = Path(dirpath) / fname
            if fp.suffix.lower() in SKIP_EXTS:
                continue
            if fp.stat().st_size > MAX_FILE_SIZE:
                continue
            try:
                rel = str(fp.relative_to(root))
                files[rel] = fp.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
    return files


async def _get_or_404(project_id: int, session: AsyncSession) -> Project:
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().first()
    if not project:
        raise HTTPException(404, "Project not found")
    return project
