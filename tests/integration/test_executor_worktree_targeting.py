import asyncio
import json
import subprocess
from pathlib import Path

import httpx2
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr

from app.container import build_container
from app.runtime import create_server
from app.settings import BridgeSettings, OpenRouterExecutorSettings
from app.transport import create_streamable_http_app
from tests.fixtures.repositories import create_git_repository

async def terminal(session, scope, job_id):
    for _ in range(300):
        data=json.loads((await session.call_tool("job_status", {**scope, "job_id": job_id})).content[0].text)["data"]
        if data["status"] in {"succeeded","failed","cancelled"}: return data
        await asyncio.sleep(.01)
    raise AssertionError("job did not finish")

def configured(tmp_path: Path, root: Path):
    worker=tmp_path/"worker.sh"
    worker.write_text("#!/bin/sh\nprintf '{\"status\":\"SUCCESS\",\"response\":\"cwd=%s\"}\\n' \"$PWD\"\n")
    worker.chmod(0o755)
    settings=BridgeSettings.model_validate({
        "server":{"tool_surface":"compact"},
        "jobs":{"database_path":tmp_path/"jobs.sqlite3"},
        "executors":{"openrouter":{"enabled":True}},
        "projects":[{"id":"project","name":"Project","repositories":[{"id":"repo","path":root,"capabilities":{"execute":True}}]}],
    })
    container=build_container(settings)
    container.executors._openrouter._settings=OpenRouterExecutorSettings(enabled=True, api_key=SecretStr("test"))
    container.executors._openrouter._python_executable=str(worker)
    container.executors._openrouter._worker_path=worker
    return settings, container, create_streamable_http_app(create_server(container), settings, container)

@pytest.mark.asyncio
async def test_openrouter_worktree_selector_uses_linked_cwd_and_no_selector_uses_canonical(tmp_path):
    root=create_git_repository(tmp_path,"repo")
    linked=tmp_path/"linked"
    subprocess.run(["git","worktree","add","-b","feature/linked",str(linked)],cwd=root,check=True,capture_output=True,text=True)
    _,_,app=configured(tmp_path,root)
    scope={"project_id":"project","repository_id":"repo"}
    async with app.router.lifespan_context(app):
      async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app),base_url="http://127.0.0.1") as client:
       async with streamable_http_client("http://127.0.0.1/mcp",http_client=client) as streams:
        async with ClientSession(*streams) as session:
         await session.initialize()
         for branch,expected in [(None,root.resolve()),("feature/linked",linked.resolve())]:
          args={**scope,"task":"inspect","task_kind":"review","executor":"openrouter"}
          if branch: args["worktree_branch"]=branch
          res=json.loads((await session.call_tool("bridge_call",{"tool_name":"executor_start","arguments":args})).content[0].text)
          started=res["data"]
          assert (await terminal(session,scope,started["job_id"]))["status"]=="succeeded"
          out=json.loads((await session.call_tool("job_output",{**scope,"job_id":started["job_id"]})).content[0].text)["data"]
          assert f"cwd={expected}" in out["stdout"]


@pytest.mark.asyncio
async def test_openrouter_worktree_selector_fail_closed_inputs(tmp_path):
    root=create_git_repository(tmp_path,"repo")
    _,_,app=configured(tmp_path,root)
    scope={"project_id":"project","repository_id":"repo"}
    async with app.router.lifespan_context(app):
      async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app),base_url="http://127.0.0.1") as client:
       async with streamable_http_client("http://127.0.0.1/mcp",http_client=client) as streams:
        async with ClientSession(*streams) as session:
         await session.initialize()
         cases=[
          {**scope,"task":"x","task_kind":"review","executor":"openrouter","worktree_branch":"feature/missing"},
          {**scope,"task":"x","task_kind":"review","executor":"codex","worktree_branch":"feature/missing"},
          {**scope,"task":"x","task_kind":"review","executor":"openrouter","worktree_path":str(tmp_path)},
         ]
         for args in cases:
          res=json.loads((await session.call_tool("bridge_call",{"tool_name":"executor_start","arguments":args})).content[0].text)
          assert res.get("isError") is True or "error" in res


@pytest.mark.asyncio
async def test_openrouter_worktree_selector_rejects_symlinked_foreign_worktree(tmp_path):
    root=create_git_repository(tmp_path,"repo")
    linked=tmp_path/"linked"
    subprocess.run(["git","worktree","add","-b","feature/safe",str(linked)],cwd=root,check=True,capture_output=True,text=True)
    foreign=create_git_repository(tmp_path,"foreign")
    import shutil
    shutil.rmtree(linked)
    linked.symlink_to(foreign,target_is_directory=True)
    _,_,app=configured(tmp_path,root)
    scope={"project_id":"project","repository_id":"repo"}
    async with app.router.lifespan_context(app):
      async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app),base_url="http://127.0.0.1") as client:
       async with streamable_http_client("http://127.0.0.1/mcp",http_client=client) as streams:
        async with ClientSession(*streams) as session:
         await session.initialize()
         args={**scope,"task":"x","task_kind":"review","executor":"openrouter","worktree_branch":"feature/safe"}
         res=json.loads((await session.call_tool("bridge_call",{"tool_name":"executor_start","arguments":args})).content[0].text)
         assert res.get("isError") is True or "error" in res


@pytest.mark.asyncio
async def test_worktree_selector_keeps_logical_repo_serialization_and_idempotency(tmp_path):
    root=create_git_repository(tmp_path,"repo")
    linked=tmp_path/"linked"
    subprocess.run(["git","worktree","add","-b","feature/linked",str(linked)],cwd=root,check=True,capture_output=True,text=True)
    worker=tmp_path/"worker.sh"
    worker.write_text("#!/bin/sh\nsleep .35\nprintf '{\"status\":\"SUCCESS\",\"response\":\"cwd=%s\"}\\n' \"$PWD\"\n")
    worker.chmod(0o755)
    settings=BridgeSettings.model_validate({"server":{"tool_surface":"compact"},"jobs":{"database_path":tmp_path/"jobs.sqlite3"},"executors":{"openrouter":{"enabled":True}},"projects":[{"id":"project","name":"Project","repositories":[{"id":"repo","path":root,"capabilities":{"execute":True}}]}]})
    container=build_container(settings)
    container.executors._openrouter._settings=OpenRouterExecutorSettings(enabled=True,api_key=SecretStr("test"))
    container.executors._openrouter._python_executable=str(worker)
    container.executors._openrouter._worker_path=worker
    app=create_streamable_http_app(create_server(container),settings,container)
    scope={"project_id":"project","repository_id":"repo"}
    async with app.router.lifespan_context(app):
      async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app),base_url="http://127.0.0.1") as client:
       async with streamable_http_client("http://127.0.0.1/mcp",http_client=client) as streams:
        async with ClientSession(*streams) as session:
         await session.initialize()
         def start_args(task,**extra): return {**scope,"task":task,"task_kind":"review","executor":"openrouter",**extra}
         first=(json.loads((await session.call_tool("bridge_call",{"tool_name":"executor_start","arguments":start_args("one")})).content[0].text))["data"]
         for _ in range(200):
          st=json.loads((await session.call_tool("job_status",{**scope,"job_id":first["job_id"]})).content[0].text)["data"]
          if st["status"]=="running": break
          await asyncio.sleep(.01)
         assert st["status"]=="running"
         second=(json.loads((await session.call_tool("bridge_call",{"tool_name":"executor_start","arguments":start_args("two",worktree_branch="feature/linked")})).content[0].text))["data"]
         st2=json.loads((await session.call_tool("job_status",{**scope,"job_id":second["job_id"]})).content[0].text)["data"]
         assert st2["status"]=="queued"
         assert (await terminal(session,scope,first["job_id"]))["status"]=="succeeded"
         assert (await terminal(session,scope,second["job_id"]))["status"]=="succeeded"
         idem=(json.loads((await session.call_tool("bridge_call",{"tool_name":"executor_start","arguments":start_args("idem",idempotency_key="logical-key")})).content[0].text))["data"]
         conflict=json.loads((await session.call_tool("bridge_call",{"tool_name":"executor_start","arguments":start_args("idem",idempotency_key="logical-key",worktree_branch="feature/linked")})).content[0].text)
         assert conflict.get("isError") is True or "error" in conflict
         await terminal(session,scope,idem["job_id"])


@pytest.mark.asyncio
async def test_openrouter_worktree_selector_does_not_select_detached_worktree(tmp_path):
    root=create_git_repository(tmp_path,"repo")
    linked=tmp_path/"detached"
    subprocess.run(["git","worktree","add","-b","feature/detached",str(linked)],cwd=root,check=True,capture_output=True,text=True)
    subprocess.run(["git","checkout","--detach"],cwd=linked,check=True,capture_output=True,text=True)
    _,_,app=configured(tmp_path,root)
    scope={"project_id":"project","repository_id":"repo"}
    async with app.router.lifespan_context(app):
      async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app),base_url="http://127.0.0.1") as client:
       async with streamable_http_client("http://127.0.0.1/mcp",http_client=client) as streams:
        async with ClientSession(*streams) as session:
         await session.initialize()
         args={**scope,"task":"x","task_kind":"review","executor":"openrouter","worktree_branch":"feature/detached"}
         res=json.loads((await session.call_tool("bridge_call",{"tool_name":"executor_start","arguments":args})).content[0].text)
         assert res.get("isError") is True or "error" in res


@pytest.mark.asyncio
async def test_queued_selector_rejects_moved_worktree_replaced_by_symlink(tmp_path):
    root=create_git_repository(tmp_path,"repo")
    old=tmp_path/"linked-old"
    new=tmp_path/"linked-new"
    subprocess.run(["git","worktree","add","-b","feature/move",str(old)],cwd=root,check=True,capture_output=True,text=True)
    worker=tmp_path/"worker.sh"
    worker.write_text("#!/bin/sh\nsleep .35\nprintf '{\"status\":\"SUCCESS\",\"response\":\"cwd=%s\"}\\n' \"$PWD\"\n")
    worker.chmod(0o755)
    settings=BridgeSettings.model_validate({"server":{"tool_surface":"compact"},"jobs":{"database_path":tmp_path/"jobs.sqlite3"},"executors":{"openrouter":{"enabled":True}},"projects":[{"id":"project","name":"Project","repositories":[{"id":"repo","path":root,"capabilities":{"execute":True}}]}]})
    container=build_container(settings)
    container.executors._openrouter._settings=OpenRouterExecutorSettings(enabled=True,api_key=SecretStr("test"))
    container.executors._openrouter._python_executable=str(worker)
    container.executors._openrouter._worker_path=worker
    app=create_streamable_http_app(create_server(container),settings,container)
    scope={"project_id":"project","repository_id":"repo"}
    async with app.router.lifespan_context(app):
      async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app),base_url="http://127.0.0.1") as client:
       async with streamable_http_client("http://127.0.0.1/mcp",http_client=client) as streams:
        async with ClientSession(*streams) as session:
         await session.initialize()
         first=(json.loads((await session.call_tool("bridge_call",{"tool_name":"executor_start","arguments":{**scope,"task":"block","task_kind":"review","executor":"openrouter"}})).content[0].text))["data"]
         for _ in range(200):
          first_state=json.loads((await session.call_tool("job_status",{**scope,"job_id":first["job_id"]})).content[0].text)["data"]
          if first_state["status"]=="running": break
          await asyncio.sleep(.01)
         assert first_state["status"]=="running"
         second=(json.loads((await session.call_tool("bridge_call",{"tool_name":"executor_start","arguments":{**scope,"task":"must-not-run","task_kind":"review","executor":"openrouter","worktree_branch":"feature/move"}})).content[0].text))["data"]
         second_state=json.loads((await session.call_tool("job_status",{**scope,"job_id":second["job_id"]})).content[0].text)["data"]
         assert second_state["status"]=="queued"
         subprocess.run(["git","worktree","move",str(old),str(new)],cwd=root,check=True,capture_output=True,text=True)
         old.symlink_to(new,target_is_directory=True)
         assert (await terminal(session,scope,first["job_id"]))["status"]=="succeeded"
         terminal_second=await terminal(session,scope,second["job_id"])
         assert terminal_second["status"]=="failed"
         assert terminal_second["failure_reason"]=="execution_root_unavailable"
