import copy
import json
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi import Query as QueryParam
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import model, security, store, tools, web
from .skills import SKILLS


@asynccontextmanager
async def lifespan(app):
    store.connect().close()
    with jobs_lock:
        jobs.clear()
        for job in reversed(store.research()):
            if job["status"] in ("running", "cancelling"):
                job.update(
                    status="interrupted",
                    result="Server restarted before this research finished. Launch a new run to retry.",
                )
                store.save_job(job)
            jobs[job["id"]] = job
    threading.Thread(target=model.load, daemon=True).start()
    yield


app = FastAPI(title="Happy · Personal AI", lifespan=lifespan)
app.add_middleware(security.GuardMiddleware)
app.include_router(security.router)
jobs = {}
jobs_lock = threading.RLock()


class InputModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class Message(InputModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=12000)


class Chat(InputModel):
    message: str = Field(min_length=1, max_length=4000)
    skill: str = "skill-001"
    web: bool = False
    history: list[Message] = Field(default_factory=list, max_length=10)


class KnowledgeBackup(BaseModel):
    version: Literal[1] = 1
    notes: list["Note"] = Field(max_length=1000)


class Query(InputModel):
    query: str = Field(min_length=1, max_length=500)


class ResearchQuery(Query):
    source: Literal["web", "knowledge"] = "web"


class Note(InputModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=30000)
    source: str = Field(default="Note", max_length=2000)


class ToolRequest(InputModel):
    # Preserve indentation and leading/trailing lines in utility input.
    model_config = ConfigDict(str_strip_whitespace=False)
    tool: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=30000)
    other: str = Field(default="", max_length=30000)


KnowledgeBackup.model_rebuild()


@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.get("/api/tools")
def tool_catalog():
    return tools.CATALOG


@app.post("/api/tools/run")
def run_tool(q: ToolRequest):
    if q.tool not in {t["id"] for t in tools.CATALOG}:
        raise HTTPException(404, "Unknown tool")
    try:
        output = tools.execute(q.tool, q.text, q.other)
        return {
            "output": output,
            "generated": False,
            "engine": "deterministic",
            "tool": q.tool,
        }
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.put("/api/knowledge/{note_id}")
def edit_knowledge(note_id: int, note: Note):
    with store.transaction() as db:
        if not db.execute(
            "UPDATE knowledge SET title=?, content=?, source=? WHERE id=?",
            (note.title, note.content, note.source, note_id),
        ).rowcount:
            raise HTTPException(404, "Memory not found")
    return {"id": note_id}


@app.get("/api/status")
def status():
    with jobs_lock:
        active = sum(j["status"] in ("running", "cancelling") for j in jobs.values())
    return {
        **model.state,
        "skills": len(SKILLS),
        "memories": len(store.notes()),
        "agents": active,
        "tools": len(tools.CATALOG),
        "protected": security.enabled(),
    }


@app.get("/api/skills")
def skills():
    return SKILLS


@app.get("/api/knowledge")
def knowledge(q: str = QueryParam(default="", max_length=500)):
    return store.notes(q)


@app.post("/api/knowledge")
def save(note: Note):
    return {"id": store.save(note.title, note.content, note.source)}


@app.delete("/api/knowledge/{note_id}")
def delete(note_id: int):
    with store.transaction() as db:
        if not db.execute("DELETE FROM knowledge WHERE id=?", (note_id,)).rowcount:
            raise HTTPException(404, "Memory not found")
    return {"ok": True}


@app.get("/api/knowledge/export")
def export_knowledge():
    data = {"version": 1, "notes": store.notes()}
    return Response(
        json.dumps(data, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="happy-knowledge.json"'},
    )


@app.post("/api/knowledge/import")
def import_knowledge(backup: KnowledgeBackup):
    return {"added": store.import_notes([n.model_dump() for n in backup.notes])}


@app.get("/api/conversation")
def conversation():
    return store.conversation()


@app.delete("/api/conversation")
def clear_conversation():
    with store.transaction() as db:
        db.execute("DELETE FROM conversation")
    return {"ok": True}


@app.post("/api/search")
def search(q: Query):
    try:
        return web.search(q.query)
    except Exception as e:
        raise HTTPException(502, f"Search unavailable: {e}")


@app.post("/api/browse")
def browse(q: Query):
    try:
        return web.browse(q.query)
    except Exception as e:
        raise HTTPException(400, f"Cannot read page: {e}")


@app.post("/api/chat")
def chat(q: Chat):
    skill = next((s for s in SKILLS if s["id"] == q.skill), None)
    if not skill:
        raise HTTPException(400, "Unknown skill")
    sources = [
        {"title": n["title"], "url": n["source"], "content": n["content"][:1500]}
        for n in store.retrieve(q.message)
    ]
    warning = None
    if q.web:
        try:
            sources += web.search(q.message)
        except Exception:
            warning = "Web search unavailable. Answer uses local context only."
    context = "\n\n".join(
        f"[{i}] {s['title']} ({s['url']})\n{s['content'][:1000]}"
        for i, s in enumerate(sources, 1)
    )
    try:
        answer = model.reply(
            q.message, skill["prompt"], context, [m.model_dump() for m in q.history]
        )
    except Exception as e:
        raise HTTPException(503, f"Inference failed: {e}")
    store.append_exchange(
        {"role": "user", "content": q.message},
        {
            "role": "assistant",
            "content": answer,
            "sources": sources,
            "warning": warning,
        },
    )
    return {
        "answer": answer,
        "sources": sources,
        "warning": warning,
        "generated": model.llm is not None,
    }


class ResearchCancelled(Exception):
    pass


def update_job(job_id, step=None, **changes):
    with jobs_lock:
        job = jobs[job_id]
        if job["status"] == "cancelling":
            raise ResearchCancelled()
        job.update(changes)
        if step:
            job["steps"].append(step)
        store.save_job(job)


def run_agent(job_id, topic, source_mode="web"):
    try:
        if source_mode == "knowledge":
            update_job(job_id, "Researcher · Finding relevant saved knowledge")
            sources = [
                {
                    "title": n["title"],
                    "url": n["source"],
                    "content": n["content"][:3500],
                }
                for n in store.retrieve(topic)
            ]
            if not sources:
                raise ValueError(
                    "No matching saved notes. Add knowledge or try keywords from a saved note."
                )
            update_job(
                job_id,
                "Reader · Collected matching local notes",
                sources=copy.deepcopy(sources),
            )
        else:
            update_job(job_id, "Researcher · Searching public sources")
            sources = web.search(topic)
            if not sources:
                raise ValueError("No sources found. Try a more specific topic.")
            update_job(
                job_id,
                "Reader · Reading up to three source pages",
                sources=copy.deepcopy(sources),
            )
            for source in sources[:3]:
                update_job(job_id)  # Cooperative cancellation checkpoint.
                try:
                    source["content"] = web.browse(source["url"])["content"][:3500]
                except Exception:
                    update_job(
                        job_id, "Reader · Page unavailable; using search excerpt"
                    )
            update_job(job_id, sources=copy.deepcopy(sources))
        context = "\n\n".join(
            f"[{i}] {s['title']} {s['url']}\n{s['content'][:1200]}"
            for i, s in enumerate(sources, 1)
        )
        update_job(
            job_id,
            "Analyst · Synthesizing evidence"
            if model.llm
            else "Analyst · Model offline; compiling source excerpts",
        )
        result = model.reply(
            topic,
            "Produce a concise research brief with numbered citations, key findings, and uncertainties.",
            context,
        )
        update_job(
            job_id,
            "Complete · Review your brief before saving to knowledge",
            result=result,
            status="complete",
        )
    except ResearchCancelled:
        with jobs_lock:
            jobs[job_id].update(
                status="cancelled", result="Research cancelled. No knowledge was saved."
            )
            store.save_job(jobs[job_id])
    except Exception as e:
        with jobs_lock:
            cancelled = jobs[job_id]["status"] == "cancelling"
            jobs[job_id].update(
                status="cancelled" if cancelled else "failed",
                result="Research cancelled. No knowledge was saved."
                if cancelled
                else str(e),
            )
            store.save_job(jobs[job_id])


@app.post("/api/agents")
def start_agent(q: ResearchQuery):
    with jobs_lock:
        if sum(j["status"] in ("running", "cancelling") for j in jobs.values()) >= 2:
            raise HTTPException(429, "Two agents are already running.")
        job_id = uuid.uuid4().hex
        jobs[job_id] = {
            "id": job_id,
            "topic": q.query,
            "source": q.source,
            "status": "running",
            "steps": ["Planner · Research goal accepted"],
            "sources": [],
            "result": "",
        }
        store.save_job(jobs[job_id])
        threading.Thread(
            target=run_agent, args=(job_id, q.query, q.source), daemon=True
        ).start()
        return copy.deepcopy(jobs[job_id])


@app.post("/api/agents/{job_id}/cancel")
def cancel_agent(job_id: str):
    with jobs_lock:
        if job_id not in jobs:
            raise HTTPException(404, "Research not found")
        if jobs[job_id]["status"] == "running":
            jobs[job_id]["status"] = "cancelling"
            jobs[job_id]["steps"].append(
                "Cancellation requested · Waiting for the current operation to return"
            )
            store.save_job(jobs[job_id])
        return copy.deepcopy(jobs[job_id])


@app.post("/api/agents/{job_id}/retry")
def retry_agent(job_id: str):
    with jobs_lock:
        old = jobs.get(job_id)
        if not old:
            raise HTTPException(404, "Research not found")
        if old["status"] in ("running", "cancelling"):
            raise HTTPException(409, "Wait for this run to finish before retrying.")
        return start_agent(
            ResearchQuery(query=old["topic"], source=old.get("source", "web"))
        )


@app.delete("/api/agents/{job_id}")
def delete_agent(job_id: str):
    with jobs_lock:
        if job_id not in jobs:
            raise HTTPException(404, "Research not found")
        if jobs[job_id]["status"] in ("running", "cancelling"):
            raise HTTPException(
                409, "Cancel the run and wait for it to stop before deleting."
            )
        with store.transaction() as db:
            db.execute("DELETE FROM research WHERE id=?", (job_id,))
        del jobs[job_id]
    return {"ok": True}


@app.get("/api/agents")
def agents():
    with jobs_lock:
        return copy.deepcopy(list(jobs.values())[::-1])


app.mount(
    "/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="ui"
)
