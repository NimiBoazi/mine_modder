from __future__ import annotations

import os
import uuid
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict
import traceback
from langgraph.checkpoint.memory import MemorySaver as _MemorySaver

from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit

# Composition root: build the LangGraph and inject an event hook
from backend.agent.graph import build_graph
from backend.agent.providers.paths import find_latest_mod_jar

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("MM_SECRET", "dev")

# In dev, allow any origin; tighten in prod
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# In-memory session store; replace with Redis for scale
_sessions: Dict[str, Dict[str, Any]] = {}
# Track runs per Socket.IO session id so a refresh (new sid) resets everything
_runs_by_sid: Dict[str, set[str]] = {}
# Track the currently active run per sid to suppress emissions from stale runs
_active_run_by_sid: Dict[str, str] = {}
# Global singleton run lock: allow only one active run across all sessions
_global_active_run_id: str | None = None

# Global in-memory checkpointer to enable pause/resume across chat turns
_CHECKPOINTER = _MemorySaver()


def _find_jar(workspace: str | None) -> Path | None:
    """Use providers.paths.find_latest_mod_jar to locate newest jar for a workspace."""
    try:
        if not workspace:
            return None
        return find_latest_mod_jar(Path(workspace))
    except Exception:
        return None


def _ensure_mod_jar(workspace: str | None) -> Path | None:
    """Ensure a built mod JAR exists and return its path.

    Uses providers.paths.find_latest_mod_jar for discovery. If none exists,
    runs Gradle to build, then checks again.
    """
    try:
        if not workspace:
            return None
        ws = Path(workspace)
        # First, try to find an existing jar via the provider helper
        jar = find_latest_mod_jar(ws)
        if jar and jar.exists():
            return jar
        # Try to build the jar
        gradlew = ws / "gradlew"
        if gradlew.exists():
            try:
                gradlew.chmod(gradlew.stat().st_mode | 0o111)
            except Exception:
                pass
        subprocess.run(["./gradlew", "--no-daemon", "runData", "build"], cwd=str(ws), check=False, timeout=900)
        # Check again using the provider helper
        jar = find_latest_mod_jar(ws)
        if jar and jar.exists():
            return jar
    except Exception:
        return None
    return None



def _ensure_download_file(workspace: str | None) -> Path | None:
    """Create a bundle ZIP with this layout:

    <ws.name>.zip
    ├─ <ws.name>/          # full MDK project (post-build)
    └─ <mod-jar>.jar       # built mod jar beside the MDK folder

    The archive is created under runs/_packages.<ws.name>.zip
    """
    try:
        if not workspace:
            return None
        ws = Path(workspace)
        if not ws.exists() or not ws.is_dir():
            return None

        # Ensure we have a built jar and generated assets in the workspace
        jar_path = _ensure_mod_jar(str(ws))

        runs_root = ws.parent
        packages_dir = runs_root / "_packages"
        packages_dir.mkdir(parents=True, exist_ok=True)

        staging_dir = packages_dir / f"{ws.name}_bundle"
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        staging_dir.mkdir(parents=True, exist_ok=True)

        # Copy the entire MDK workspace into a single folder at the bundle root
        mdk_dir = staging_dir / ws.name
        shutil.copytree(str(ws), str(mdk_dir), dirs_exist_ok=True)

        # Place the mod JAR (if any) next to the MDK folder in the bundle root
        if jar_path and Path(jar_path).exists():
            shutil.copy2(str(jar_path), str(staging_dir / Path(jar_path).name))

        # Create <packages_dir>/<ws.name>.zip from the staged bundle root
        base = packages_dir / ws.name
        archive_path_str = shutil.make_archive(str(base), "zip", root_dir=str(staging_dir))

        # Cleanup staging
        try:
            shutil.rmtree(staging_dir, ignore_errors=True)
        except Exception:
            pass

        return Path(archive_path_str)
    except Exception:
        return None


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


@app.route("/download/<run_id>/<path:filename>")
def download(run_id: str, filename: str):
    ctx = _sessions.get(run_id) or {}
    candidates = []
    fp = ctx.get("file_path")
    jp = ctx.get("jar_path")
    if fp:
        candidates.append(Path(fp))
    if jp:
        candidates.append(Path(jp))
    for p in candidates:
        try:
            if p.exists() and p.name == filename:
                return send_from_directory(p.parent, p.name, as_attachment=True)
        except Exception:
            continue
    # Fallback 1: search by exact filename anywhere under runs/
    try:
        runs_dir = Path("runs")
        for p in runs_dir.rglob(filename):
            if p.is_file() and p.name == filename:
                return send_from_directory(p.parent, p.name, as_attachment=True)
    except Exception:
        pass
    # Fallback 2: if a JAR was requested but name mismatched, try serving the newest JAR for this run/workspace
    try:
        if filename.lower().endswith(".jar"):
            ws = None
            try:
                ws = ctx.get("workspace_path") or (ctx.get("state") or {}).get("workspace_path")
            except Exception:
                ws = None
            if ws:
                newest = _find_jar(ws)
                if newest and newest.exists():
                    return send_from_directory(newest.parent, newest.name, as_attachment=True)
            # As a last resort, serve the newest jar anywhere under runs/
            runs_dir = Path("runs")
            jars = [p for p in runs_dir.rglob("*.jar") if p.is_file()]
            if jars:
                jars.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                newest = jars[0]
                return send_from_directory(newest.parent, newest.name, as_attachment=True)
    except Exception:
        pass
    return ("Not found", 404)


@socketio.on("connect")
def on_connect():
    emit("connected", {"sid": request.sid})


@socketio.on("start_run")
def start_run(data):
    """Start a new graph run for this socket."""
    prompt: str = (data or {}).get("prompt") or ""
    author: str = (data or {}).get("author") or "User"
    mc_version: str | None = (data or {}).get("mc_version")
    if not prompt.strip():
        emit("error", {"message": "prompt required"})
        return

    sid = request.sid
    # Enforce single active run globally
    global _global_active_run_id
    if _global_active_run_id is not None:
        emit("error", {"message": "Another run is already in progress. Please wait until it finishes."})
        return

    # Clean the runs folder at the start of every new run (single-user mode)
    try:
        runs_dir = Path("runs")
        if runs_dir.exists():
            shutil.rmtree(runs_dir, ignore_errors=True)
        runs_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


    run_id = uuid.uuid4().hex[:12]

    # Refresh semantics: starting a run clears any previous runs for this sid
    prev_runs = _runs_by_sid.get(sid)
    if prev_runs:
        for rid in list(prev_runs):
            _sessions.pop(rid, None)
        _runs_by_sid[sid] = set()
    _runs_by_sid.setdefault(sid, set()).add(run_id)
    # Mark this run as the active one for this sid; suppress stale emissions
    _active_run_by_sid[sid] = run_id
    # Set global run lock to enforce single active run
    _global_active_run_id = run_id




    def emit_progress(event_type: str, payload: Dict[str, Any]):
        try:
            # Suppress progress from stale/background runs for this sid
            if _active_run_by_sid.get(sid) != run_id:
                return
            socketio.emit("progress", {"type": event_type, **payload, "run_id": run_id}, room=sid)
            node = payload.get("node")
            if node == "summarize_and_finish":
                st = payload.get("state") or {}
                summary = st.get("summary") or (_sessions.get(run_id) or {}).get("state", {}).get("summary")
                # Only emit mod_ready once we actually have a summary (post-node)
                if summary:
                    workspace = st.get("workspace_path") or (_sessions.get(run_id) or {}).get("state", {}).get("workspace_path")
                    # Emit explicit packaging progress so UI reflects this phase
                    socketio.emit("progress", {"type": "progress", "node": "packaging", "label": "Packaging download...", "run_id": run_id}, room=sid)
                    file_path = _ensure_download_file(workspace)
                    # Build jar internally for packaging if needed, but do not expose as a separate download link
                    _ = _ensure_mod_jar(workspace)
                    file_url = None
                    sess = _sessions.setdefault(run_id, {"sid": sid})
                    if file_path and file_path.exists():
                        sess["file_path"] = file_path
                        file_url = f"/download/{run_id}/{file_path.name}"
                    if workspace:
                        sess["workspace_path"] = workspace
                    sess["ready_emitted"] = True
                    socketio.emit("mod_ready", {"run_id": run_id, "summary": summary, "download_url": file_url}, room=sid)
                    # Clear summary in session to avoid stale summaries later
                    try:
                        sess = _sessions.get(run_id)
                        if sess and isinstance(sess.get("state"), dict):
                            sess["state"]["summary"] = ""
                    except Exception:
                        pass
        except Exception:
            pass

    app_graph = build_graph(on_event=emit_progress, checkpointer=_CHECKPOINTER)

    # Initial state minimal: prompt only; graph infers the rest
    init_state = {
        "user_input": prompt,
        "authors": [author],
        # Optional roots; graph can default these if omitted
        # "runs_root": "runs",
        # "downloads_root": "runs/_downloads",
    }
    # Allow frontend to choose MC version; override default only if provided
    if mc_version and isinstance(mc_version, str):
        init_state["mc_version"] = mc_version

    # Do not store the graph object; build a fresh, stateless graph per turn
    _sessions[run_id] = {"sid": sid, "state": init_state}

    def _run():
        global _global_active_run_id
        try:
            res = app_graph.invoke(init_state, config={"configurable": {"thread_id": run_id}})
            if not isinstance(res, dict):
                # If we paused (interrupt), fall back to the latest state from progress
                res = dict((_sessions.get(run_id) or {}).get("state") or {})

            # Determine summary + mod files
            summary = res.get("summary")
            workspace = res.get("workspace_path")
            file_path = _ensure_download_file(workspace)
            # Build jar internally for packaging if needed, but do not expose as a separate download link
            _ = _ensure_mod_jar(workspace)
            file_url = None
            sess = _sessions.setdefault(run_id, {"sid": sid})
            if file_path and file_path.exists():
                sess["file_path"] = file_path
                file_url = f"/download/{run_id}/{file_path.name}"

            _sessions[run_id]["state"] = res
            if workspace:
                _sessions[run_id]["workspace_path"] = workspace
            if not _sessions[run_id].get("ready_emitted"):
                socketio.emit("mod_ready", {"run_id": run_id, "summary": summary, "download_url": file_url}, room=sid)
                # Clear summary in session to avoid stale summaries later
                try:
                    sess = _sessions.get(run_id)
                    if sess and isinstance(sess.get("state"), dict):
                        sess["state"]["summary"] = ""
                except Exception:
                    pass
        except Exception as e:
            traceback.print_exc()
            socketio.emit("error", {"message": str(e), "run_id": run_id}, room=sid)
        finally:
            try:
                if _global_active_run_id == run_id:
                    _global_active_run_id = None
            except Exception:
                pass

    socketio.start_background_task(_run)
    emit("run_started", {"run_id": run_id})


@socketio.on("chat")
def chat(data):
    run_id: str = (data or {}).get("run_id") or ""
    message: str = (data or {}).get("message") or ""
    if not run_id or run_id not in _sessions:
        emit("error", {"message": "invalid run_id"})
        return
    if not message.strip():
        return

    sid = request.sid
    # Mark this run active for this sid during this chat turn; suppress stale emissions
    _active_run_by_sid[sid] = run_id

    ctx = _sessions[run_id]
    # Enforce that only the original socket session can use this run_id
    if ctx.get("sid") != request.sid:
        emit("error", {"message": "stale run_id (belongs to a different session); please start a new run"})
        return
    prev_state = dict(ctx.get("state") or {})
    # Ensure workspace_path is propagated into chat turns
    if "workspace_path" not in prev_state or not (prev_state.get("workspace_path") or "").strip():
        # 1) Try session-level cached workspace
        wp = (ctx.get("workspace_path") or "").strip()
        if wp:
            prev_state["workspace_path"] = wp
        else:
            # 2) Recover from events history (init_subgraph stores workspace_path in event)
            try:
                events = list((prev_state.get("events") or []))
                for ev in reversed(events):
                    wpe = (ev.get("workspace_path") or "").strip()
                    if wpe:
                        prev_state["workspace_path"] = wpe
                        break
            except Exception:
                pass

    def emit_progress(event_type: str, payload: Dict[str, Any]):
        try:
            # Suppress progress from any run that is not the active one for this sid
            if _active_run_by_sid.get(sid) != run_id:
                return
            socketio.emit("progress", {"type": event_type, **payload, "run_id": run_id}, room=sid)
            node = payload.get("node")
            if node == "summarize_and_finish":
                st = payload.get("state") or {}
                # Persist latest state snapshot from this node for recovery
                try:
                    if isinstance(st, dict):
                        _sessions[run_id]["state"] = st
                        if st.get("workspace_path"):
                            _sessions[run_id]["workspace_path"] = st.get("workspace_path")
                except Exception:
                    pass
                summary = st.get("summary") or (_sessions.get(run_id) or {}).get("state", {}).get("summary")
                if summary:
                    workspace = st.get("workspace_path") or (_sessions.get(run_id) or {}).get("state", {}).get("workspace_path")
                    # Emit explicit packaging progress so UI reflects this phase
                    socketio.emit("progress", {"type": "progress", "node": "packaging", "label": "Packaging download...", "run_id": run_id}, room=sid)
                    file_path = _ensure_download_file(workspace)
                    # Build jar internally for packaging if needed, but do not expose as a separate download link
                    _ = _ensure_mod_jar(workspace)
                    file_url = None
                    sess = _sessions.setdefault(run_id, {"sid": sid})
                    if file_path and file_path.exists():
                        sess["file_path"] = file_path
                        file_url = f"/download/{run_id}/{file_path.name}"
                    socketio.emit("mod_ready", {"run_id": run_id, "summary": summary, "download_url": file_url}, room=sid)
                    # Clear summary in session to avoid stale summaries later
                    try:
                        sess = _sessions.get(run_id)
                        if sess and isinstance(sess.get("state"), dict):
                            sess["state"]["summary"] = ""
                    except Exception:
                        pass
        except Exception:
            pass

    # Build a fresh graph for this chat turn, but attach the same checkpointer so we resume from interrupts
    app_graph = build_graph(on_event=emit_progress, checkpointer=_CHECKPOINTER)

    new_state = {**prev_state, "followup_user_input": message, "followup_message": message, "awaiting_user_input": False}

    # Tell the frontend to show loading animation for this chat turn
    emit("run_started", {"run_id": run_id})

    def _run_chat():
        try:
            res = app_graph.invoke(new_state, config={"configurable": {"thread_id": run_id}})
            if not isinstance(res, dict):
                res = dict((_sessions.get(run_id) or {}).get("state") or {})
        except Exception as e:
            traceback.print_exc()
            socketio.emit("error", {"message": str(e), "run_id": run_id}, room=sid)
            return
        _sessions[run_id]["state"] = res
        # Only send an explicit reply if respond_to_user produced one; do NOT include summary to avoid UI fallback
        answer = res.get("last_user_response") or ""
        socketio.emit("chat_response", {"run_id": run_id, "message": answer}, room=sid)

    socketio.start_background_task(_run_chat)

@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    runs = _runs_by_sid.pop(sid, set())
    for rid in runs:
        _sessions.pop(rid, None)
    # No emit here; client is gone. This ensures a browser refresh (new sid)
    # starts clean without leftover state.



if __name__ == "__main__":
    # Dev server
    port = int(os.getenv("PORT", "5001"))
    socketio.run(app, host="0.0.0.0", port=port, debug=True)

