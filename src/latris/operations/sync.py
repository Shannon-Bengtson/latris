"""Remote sync transport: push/pull/fetch against a configured git remote.

These are *transport* operations, not model mutations — they never call
``auto_commit``. A pull may create a merge commit (git's own), and push/pull
return the resulting local HEAD sha so callers can report it.

The ``env`` parameter threads through to :mod:`latris.repo.git` so the
desktop layer can inject credentials (``GIT_ASKPASS`` + a one-shot token) at
call time without persisting secrets in the remote URL or git config.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from latris.operations.commit import auto_commit
from latris.repo import git
from latris.repo.project import ProjectPaths, require_project
from latris.repo.yaml_io import dump_model, load_model, load_model_from_string
from latris.schema.common import HumanActor
from latris.schema.lineage import LineageNode
from latris.schema.membership import MemberRecord, MembersFile
from latris.sync import credentials
from latris.sync.askpass import build_credential_env
from latris.sync.client import SyncClient, SyncClientError


class SyncError(RuntimeError):
    """Raised for sync-specific failures (no remote, not signed in, conflict)."""


def set_remote(url: str, *, name: str = "origin", root: Path | None = None) -> None:
    """Configure (or repoint) the *name* remote for the project at *root*."""
    paths = require_project(root)
    if git.has_remote(paths.root, name):
        git.remote_set_url(paths.root, name, url)
    else:
        git.remote_add(paths.root, name, url)


def remote_url(*, name: str = "origin", root: Path | None = None) -> str | None:
    """Return the configured URL for *name*, or ``None`` if unset."""
    paths = require_project(root)
    return git.list_remotes(paths.root).get(name)


def _require_remote(paths: Any, name: str) -> None:
    if not git.has_remote(paths.root, name):
        raise SyncError(
            f"no '{name}' remote configured. Set one with `latris sync remote <url>`."
        )


def push(
    *,
    remote: str = "origin",
    branch: str | None = None,
    env: dict[str, str] | None = None,
    root: Path | None = None,
) -> str:
    """Push the current branch to *remote*. Returns the local HEAD sha."""
    paths = require_project(root)
    _require_remote(paths, remote)
    branch = branch or git.current_branch(paths.root)
    git.push(paths.root, remote, branch, set_upstream=True, env=env)
    return git.head_sha(paths.root)


def pull(
    *,
    remote: str = "origin",
    branch: str | None = None,
    env: dict[str, str] | None = None,
    root: Path | None = None,
) -> str:
    """Fetch and merge *remote* into the current branch. Returns the HEAD sha.

    Raises :class:`SyncError` if the merge leaves unresolved conflicts (the
    interactive resolution flow lands in S4).
    """
    paths = require_project(root)
    _require_remote(paths, remote)
    git.ensure_identity(paths.root)  # a merge may create a commit
    branch = branch or git.current_branch(paths.root)
    try:
        git.pull(paths.root, remote, branch, env=env)
    except git.GitError:
        if git.has_conflicts(paths.root):
            raise SyncError(
                "pull produced a merge conflict. Resolve it manually for now — "
                "guided conflict resolution is coming."
            ) from None
        raise
    return git.head_sha(paths.root)


def fetch(
    *,
    remote: str = "origin",
    env: dict[str, str] | None = None,
    root: Path | None = None,
) -> None:
    """Fetch refs from *remote* without merging."""
    paths = require_project(root)
    _require_remote(paths, remote)
    git.fetch(paths.root, remote, env=env)


def status(*, remote: str = "origin", root: Path | None = None) -> dict[str, Any]:
    """Summarise local sync state (does not touch the network).

    Returns ``{remote, url, branch, uncommitted, ahead, behind}``. ``ahead``/
    ``behind`` are ``None`` when no upstream is configured; they reflect the
    last fetch.
    """
    paths = require_project(root)
    url = git.list_remotes(paths.root).get(remote)
    branch = git.current_branch(paths.root)
    counts = git.ahead_behind(paths.root)
    ahead, behind = counts if counts is not None else (None, None)
    return {
        "remote": remote,
        "url": url,
        "branch": branch,
        "uncommitted": git.has_uncommitted_changes(paths.root),
        "ahead": ahead,
        "behind": behind,
    }


# -- Sync broker: control plane + credentials + authed git --------------------
#
# These tie the keyring credential store, the control-plane HTTP client, and
# the git transport together. The control plane is the source of truth for
# accounts/projects/membership; provenance/members.yaml is the committed
# advisory mirror.

SYNC_PROJECT_ID_KEY = "latris.projectid"
SYNC_SERVER_KEY = "latris.server"


def _client(*, require_auth: bool = True, timeout: float = 30.0) -> SyncClient:
    url = credentials.get_server_url()
    if not url:
        raise SyncError("not connected to a sync server")
    token = credentials.get_session_token()
    if require_auth and not token:
        raise SyncError("not signed in to Latris")
    return SyncClient(url, token, timeout=timeout)


def _authed_env() -> dict[str, str]:
    user = credentials.get_gitea_username()
    token = credentials.get_gitea_token()
    if not user or not token:
        raise SyncError("not signed in to Latris")
    return build_credential_env(user, token)


def _account_actor() -> HumanActor:
    acct = credentials.get_account()
    if not acct:
        raise SyncError("not signed in to Latris")
    return HumanActor(name=acct.get("display_name") or acct["email"], email=acct.get("email"))


def login_request_code(server_url: str, email: str, intent: str = "auto") -> None:
    """Ask the control plane to email a one-time login code."""
    credentials.set_server_url(server_url)
    try:
        SyncClient(server_url).request_code(email, intent)
    except SyncClientError as exc:
        raise SyncError(str(exc)) from exc


def login_verify(
    server_url: str,
    email: str,
    code: str,
    device: str | None = None,
    *,
    intent: str = "auto",
    first_name: str | None = None,
    last_name: str | None = None,
    organisation: str | None = None,
    country: str | None = None,
    role: str | None = None,
    industry: str | None = None,
) -> dict:
    """Exchange a code for tokens, persisting them in the keyring. Returns the account."""
    try:
        data = SyncClient(server_url).verify_code(
            email,
            code,
            device,
            intent=intent,
            first_name=first_name,
            last_name=last_name,
            organisation=organisation,
            country=country,
            role=role,
            industry=industry,
        )
    except SyncClientError as exc:
        raise SyncError(str(exc)) from exc
    credentials.store_session(
        server_url=server_url,
        session_token=data["session_token"],
        gitea_token=data["gitea"]["token"],
        gitea_username=data["gitea"]["username"],
        account=data["account"],
    )
    credentials.set_last_validated(_now_iso())  # a fresh login is a validation
    return data["account"]


def update_profile(
    first_name: str | None,
    last_name: str | None,
    organisation: str | None,
    country: str | None = None,
    role: str | None = None,
    industry: str | None = None,
) -> dict:
    """Update the signed-in account's profile; refresh the cached account."""
    try:
        account = _client().update_profile(
            first_name, last_name, organisation, country, role, industry
        )
    except SyncClientError as exc:
        raise SyncError(str(exc)) from exc
    credentials.update_cached_account(account)
    return account


def current_account() -> dict | None:
    return credentials.get_account() if credentials.is_logged_in() else None


# -- Access re-validation (the launch-time gate) ------------------------------
#
# The desktop already requires sign-in to reach the workspace, but the cached
# session never expires locally. validate_access re-checks the account against
# the control plane on launch so access can be revoked (account suspended /
# session revoked / expired), while tolerating offline use within a grace
# window so a partner on a plane isn't locked out.

GRACE_DAYS = 14


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _within_grace(iso: str | None) -> bool:
    if not iso:
        return False
    try:
        ts = datetime.fromisoformat(iso)
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return datetime.now(UTC) - ts <= timedelta(days=GRACE_DAYS)


def validate_access() -> dict:
    """Re-check the signed-in account against the control plane, with offline grace.

    Returns ``{"state": ..., "account": ...}`` where state is:

    - ``"anon"`` — not signed in.
    - ``"valid"`` — online re-check passed (cache + ``last_validated`` refreshed).
    - ``"revoked"`` — control plane rejected the session/account (creds cleared).
    - ``"offline_ok"`` — couldn't reach the server but within the grace window.
    - ``"offline_expired"`` — couldn't reach the server and grace has lapsed.
    """
    if not credentials.is_logged_in():
        return {"state": "anon", "account": None}
    try:
        client = _client(timeout=5.0)
    except SyncError:
        return {"state": "anon", "account": None}
    try:
        account = client.validate()
    except SyncClientError as exc:
        if exc.status_code in (401, 403):
            credentials.clear()
            return {"state": "revoked", "account": None}
        # Transport failure (offline). Start the grace clock if unset, then
        # allow cached use until it lapses.
        last = credentials.get_last_validated()
        if last is None:
            last = _now_iso()
            credentials.set_last_validated(last)
        cached = credentials.get_account()
        if _within_grace(last):
            return {"state": "offline_ok", "account": cached}
        return {"state": "offline_expired", "account": cached}
    credentials.update_cached_account(account)
    credentials.set_last_validated(_now_iso())
    return {"state": "valid", "account": account}


def logout() -> None:
    with contextlib.suppress(SyncError, SyncClientError):
        _client().logout()
    credentials.clear()


def list_remote_projects() -> list[dict]:
    try:
        return _client().me().get("projects", [])
    except SyncClientError as exc:
        raise SyncError(str(exc)) from exc


def project_id(*, root: Path | None = None) -> str | None:
    paths = require_project(root)
    return git.get_config(paths.root, SYNC_PROJECT_ID_KEY)


def _record_project_link(paths: ProjectPaths, proj: dict) -> None:
    git.set_config(paths.root, SYNC_PROJECT_ID_KEY, proj["id"])
    server = credentials.get_server_url()
    if server:
        git.set_config(paths.root, SYNC_SERVER_KEY, server)


def read_members(*, root: Path | None = None) -> list[MemberRecord]:
    paths = require_project(root)
    if not paths.members_yaml.exists():
        return []
    return load_model(MembersFile, paths.members_yaml).members


def _write_members(paths: ProjectPaths, records: list[MemberRecord]) -> None:
    dump_model(MembersFile(members=records), paths.members_yaml)


def share(name: str, *, root: Path | None = None) -> dict:
    """Create a remote project, wire the remote, record ownership, first push."""
    paths = require_project(root)
    client = _client()
    try:
        proj = client.create_project(name)
    except SyncClientError as exc:
        raise SyncError(str(exc)) from exc
    owner = _account_actor()
    acct = credentials.get_account() or {}
    git.set_local_identity(paths.root, owner.name, owner.email or "")
    set_remote(proj["clone_url"], root=root)
    _record_project_link(paths, proj)
    _write_members(
        paths,
        [MemberRecord(actor=owner, account_id=acct.get("id"), role="owner", added_by=owner)],
    )
    auto_commit(
        paths.root,
        subject=f'Shared project "{name}" — recorded ownership',
        body=f"project: {proj['id']}",
        paths=[paths.members_yaml],
    )
    git.push(paths.root, "origin", git.current_branch(paths.root), set_upstream=True, env=_authed_env())
    return proj


def clone_project(remote_project_id: str, dest: Path) -> Path:
    """Clone a shared project into *dest* and stamp its sync identity."""
    client = _client()
    try:
        proj = client.get_project(remote_project_id)
    except SyncClientError as exc:
        raise SyncError(str(exc)) from exc
    git.clone(proj["clone_url"], dest, env=_authed_env())
    owner = _account_actor()
    git.set_local_identity(dest, owner.name, owner.email or "")
    git.set_config(dest, SYNC_PROJECT_ID_KEY, remote_project_id)
    server = credentials.get_server_url()
    if server:
        git.set_config(dest, SYNC_SERVER_KEY, server)
    return dest


def authed_push(*, remote: str = "origin", root: Path | None = None) -> str:
    return push(remote=remote, env=_authed_env(), root=root)


def authed_pull(*, remote: str = "origin", root: Path | None = None) -> dict:
    """Pull with credentials. Returns ``{"status": "ok"|"conflict", "head"?}``."""
    paths = require_project(root)
    env = _authed_env()
    try:
        head = pull(remote=remote, env=env, root=root)
        return {"status": "ok", "head": head}
    except SyncError:
        if git.has_conflicts(paths.root):
            return {"status": "conflict"}
        raise


def resolve_conflict(strategy: str, *, root: Path | None = None) -> str:
    """Resolve a merge conflict by keeping one side. *strategy* is 'ours'/'theirs'."""
    paths = require_project(root)
    if not git.has_conflicts(paths.root):
        raise SyncError("there is no conflict to resolve")
    git.ensure_identity(paths.root)
    return git.complete_merge_with(paths.root, strategy)


def abort_conflict(*, root: Path | None = None) -> None:
    paths = require_project(root)
    git.abort_merge(paths.root)


def sync_status(*, remote: str = "origin", root: Path | None = None) -> dict:
    """Transport status enriched with sync/login state for the GUI."""
    paths = require_project(root)
    base = status(remote=remote, root=root)
    base.update(
        {
            "logged_in": credentials.is_logged_in(),
            "account": credentials.get_account(),
            "server_url": credentials.get_server_url(),
            "project_id": git.get_config(paths.root, SYNC_PROJECT_ID_KEY),
            "shared": git.get_config(paths.root, SYNC_PROJECT_ID_KEY) is not None,
            "has_conflict": git.has_conflicts(paths.root),
        }
    )
    return base


# -- Per-version sync: publish / get-latest / add-to-workspace ----------------
#
# Each lineage version is a git branch. "Publishing" a version pushes that one
# branch; "getting latest" fast-forwards it; a version a collaborator published
# that isn't local yet is a "ghost". All state is computed from the last fetch
# (no network) except refresh_sync, which fetches first.


def version_sync_states(*, remote: str = "origin", root: Path | None = None) -> dict:
    """Per-version sync state vs *remote*, from the last fetch (no network).

    Returns ``{sync_state, ghosts, shared}``:
    - ``sync_state``: ``{version_id: {published, ahead, behind, state}}`` where
      *state* ∈ {local_only, in_sync, unpublished, updates, diverged}.
    - ``ghosts``: remote-only versions not in the local tree.
    - ``shared``: whether the project is linked to a remote project.

    Safe to call unconditionally — short-circuits to all-local when the project
    is unshared, and reads only cached refs otherwise.
    """
    from latris.operations.lineage import nodes_and_branches

    paths = require_project(root)
    root_p = paths.root

    _, branch_for_node = nodes_and_branches(root_p)
    shared = git.get_config(root_p, SYNC_PROJECT_ID_KEY) is not None

    if not shared or not git.has_remote(root_p, remote):
        return {
            "sync_state": {
                vid: {"published": False, "ahead": 0, "behind": 0, "state": "local_only"}
                for vid in branch_for_node
            },
            "ghosts": [],
            "shared": shared,
        }

    remote_branches = set(git.list_remote_branches(root_p, remote))
    local_branches = set(branch_for_node.values())

    sync_state: dict[str, dict[str, Any]] = {}
    for vid, branch in branch_for_node.items():
        if branch not in remote_branches:
            sync_state[vid] = {"published": False, "ahead": 0, "behind": 0, "state": "local_only"}
            continue
        counts = git.branch_ahead_behind(root_p, branch, f"{remote}/{branch}")
        ahead, behind = counts if counts is not None else (0, 0)
        if ahead and behind:
            state = "diverged"
        elif ahead:
            state = "unpublished"
        elif behind:
            state = "updates"
        else:
            state = "in_sync"
        sync_state[vid] = {"published": True, "ahead": ahead, "behind": behind, "state": state}

    ghosts: list[dict[str, Any]] = []
    for branch in sorted(remote_branches - local_branches):
        if branch != "main" and not branch.startswith("lineage/"):
            continue
        ghosts.append(_ghost_for_branch(root_p, remote, branch))

    return {"sync_state": sync_state, "ghosts": ghosts, "shared": shared}


def _ghost_for_branch(root: Path, remote: str, branch: str) -> dict[str, Any]:
    """Describe a remote-only version from its lineage-node.yaml at the remote ref."""
    info: dict[str, Any] = {"branch": branch}
    try:
        text = git.show_file(root, f"{remote}/{branch}", ".graph-tooling/lineage-node.yaml")
        node = load_model_from_string(LineageNode, text)
        info.update(
            {
                "version_id": node.id,
                "name": node.name,
                "maturity": node.maturity,
                "created_by": node.created_by.model_dump(mode="json"),
            }
        )
    except Exception:
        info.update(
            {"version_id": None, "name": branch, "maturity": "proposed", "created_by": None}
        )
    return info


def refresh_sync(
    *, remote: str = "origin", env: dict[str, str] | None = None, root: Path | None = None
) -> dict:
    """Fetch all remote refs (network) then recompute per-version state."""
    paths = require_project(root)
    if git.has_remote(paths.root, remote):
        git.fetch(paths.root, remote, env=env)
    return version_sync_states(remote=remote, root=root)


def _resolve_branch(version_query: str, root: Path) -> tuple[str, str]:
    """Resolve a version query to ``(version_id, branch)``."""
    from latris.operations.lineage import (
        _branch_for_version,
        _resolve_version,
        get_lineage_tree,
    )

    tree = get_lineage_tree(root)
    node = _resolve_version(version_query, tree["nodes"])
    vid = node["id"] if isinstance(node, dict) else node.id
    return vid, _branch_for_version(node, tree)


def publish_version(
    version_query: str,
    *,
    remote: str = "origin",
    env: dict[str, str] | None = None,
    root: Path | None = None,
) -> dict:
    """Publish a single version: push its branch to *remote* (sets upstream).

    Returns ``{version_id, branch, head}``.
    """
    paths = require_project(root)
    _require_remote(paths, remote)
    vid, branch = _resolve_branch(version_query, paths.root)
    git.push(paths.root, remote, branch, set_upstream=True, env=env)
    head = git.run_git(["rev-parse", branch], cwd=paths.root).stdout.strip()
    return {"version_id": vid, "branch": branch, "head": head}


def get_latest(
    version_query: str,
    *,
    remote: str = "origin",
    env: dict[str, str] | None = None,
    root: Path | None = None,
) -> dict:
    """Fast-forward a published version to the remote. Returns ``{branch, status, head}``.

    If it's the current branch, pulls (merge into the working tree). Otherwise
    fast-forwards the local ref without touching the working tree. Divergence is
    routed to Reconcile, not here — a non-ff update raises :class:`SyncError`.
    """
    paths = require_project(root)
    _require_remote(paths, remote)
    vid, branch = _resolve_branch(version_query, paths.root)
    if branch == git.current_branch(paths.root):
        try:
            head = pull(remote=remote, branch=branch, env=env, root=root)
        except SyncError:
            if git.has_conflicts(paths.root):
                return {"branch": branch, "version_id": vid, "status": "conflict"}
            raise
        return {"branch": branch, "version_id": vid, "status": "ok", "head": head}
    try:
        git.fetch_branch(paths.root, remote, f"{branch}:{branch}", env=env)
    except git.GitError as exc:
        raise SyncError(
            "this version has diverged from the shared copy — reconcile it instead "
            "of getting the latest."
        ) from exc
    head = git.run_git(["rev-parse", branch], cwd=paths.root).stdout.strip()
    return {"branch": branch, "version_id": vid, "status": "ok", "head": head}


def add_to_workspace(
    branch: str,
    *,
    remote: str = "origin",
    env: dict[str, str] | None = None,
    root: Path | None = None,
) -> dict:
    """Materialise a remote-only version as a local branch (no checkout).

    Returns ``{branch, version_id}``. Idempotent — a no-op if already local.
    """
    paths = require_project(root)
    _require_remote(paths, remote)
    if branch not in git.list_branches(paths.root):
        git.fetch_branch(paths.root, remote, f"{branch}:{branch}", env=env)
    version_id: str | None = None
    try:
        text = git.show_file(paths.root, branch, ".graph-tooling/lineage-node.yaml")
        version_id = load_model_from_string(LineageNode, text).id
    except Exception:
        version_id = None
    return {"branch": branch, "version_id": version_id}


# -- Authed wrappers (inject keyring credentials; used by the server) ----------


def authed_refresh_sync(*, remote: str = "origin", root: Path | None = None) -> dict:
    return refresh_sync(remote=remote, env=_authed_env(), root=root)


def authed_publish_version(version_query: str, *, remote: str = "origin", root: Path | None = None) -> dict:
    return publish_version(version_query, remote=remote, env=_authed_env(), root=root)


def authed_get_latest(version_query: str, *, remote: str = "origin", root: Path | None = None) -> dict:
    return get_latest(version_query, remote=remote, env=_authed_env(), root=root)


def authed_add_to_workspace(branch: str, *, remote: str = "origin", root: Path | None = None) -> dict:
    return add_to_workspace(branch, remote=remote, env=_authed_env(), root=root)


def authed_reconcile(version_query: str, keep: str, *, remote: str = "origin", root: Path | None = None) -> dict:
    """Reconcile a diverged version (keep mine publishes, so it needs creds)."""
    from latris.operations import lineage

    return lineage.reconcile(version_query, keep, remote=remote, env=_authed_env(), root=root)


# -- Member management (control plane authoritative; members.yaml mirror) -----


def _refresh_members_mirror(paths: ProjectPaths, client: SyncClient, pid: str) -> None:
    try:
        detail = client.get_project(pid)
    except SyncClientError:
        return
    me = _account_actor()
    records: list[MemberRecord] = []
    for m in detail.get("members", []):
        if not m.get("email"):
            continue
        actor = HumanActor(name=m.get("display_name") or m["email"], email=m["email"])
        records.append(MemberRecord(actor=actor, account_id=m.get("account_id"), role=m["role"], added_by=me))
    _write_members(paths, records)
    if git.has_uncommitted_changes(paths.root):
        auto_commit(paths.root, subject="Updated project membership", body="", paths=[paths.members_yaml])


def _member_op(action, *, root: Path | None):
    paths = require_project(root)
    pid = project_id(root=root)
    if not pid:
        raise SyncError("this project is not shared yet")
    client = _client()
    try:
        result = action(client, pid)
    except SyncClientError as exc:
        raise SyncError(str(exc)) from exc
    _refresh_members_mirror(paths, client, pid)
    return result, pid


def add_member(email: str, role: str = "collaborator", *, root: Path | None = None) -> dict:
    result, _ = _member_op(lambda c, pid: c.add_member(pid, email, role), root=root)
    return result


def update_member(account_id: str, role: str, *, root: Path | None = None) -> dict:
    result, _ = _member_op(lambda c, pid: c.update_member(pid, account_id, role), root=root)
    return result


def remove_member(account_id: str, *, root: Path | None = None) -> dict:
    result, _ = _member_op(lambda c, pid: c.remove_member(pid, account_id), root=root)
    return result
