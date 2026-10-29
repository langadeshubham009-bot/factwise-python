"""Concrete implementations of UserBase, TeamBase and ProjectBoardBase.

Services share one ``Repository`` (the persisted collections plus in-memory
indexes) so that cross-entity rules (e.g. a team admin must be a real user)
are enforced in one place.
"""
import os
from collections import defaultdict
from typing import Dict, List, Optional

from project_board_base import ProjectBoardBase
from team_base import TeamBase
from user_base import UserBase

from . import storage
from .common import (check_timestamp, dumps, new_id, now, parse, require_found,
                     require_str)
from .exceptions import ConflictError, ValidationError

MAX_TEAM_USERS = 50
TASK_STATUSES = ("OPEN", "IN_PROGRESS", "COMPLETE")


class Repository:
    """Persisted collections + lookup indexes built once on first use."""

    def __init__(self, db_dir: Optional[str] = None, out_dir: Optional[str] = None):
        self.users = storage.Collection("users", db_dir)
        self.teams = storage.Collection("teams", db_dir)
        self.boards = storage.Collection("boards", db_dir)
        self.tasks = storage.Collection("tasks", db_dir)
        self.out_dir = out_dir or storage.OUT_DIR
        self._built = False

    def _build_indexes(self) -> None:
        if self._built:
            return
        self.user_by_name: Dict[str, str] = {u["name"]: u["id"] for u in self.users.values()}
        self.team_by_name: Dict[str, str] = {t["name"]: t["id"] for t in self.teams.values()}
        self.board_by_key: Dict[tuple, str] = {
            (b["team_id"], b["name"]): b["id"] for b in self.boards.values()}
        self.tasks_by_board: Dict[str, List[str]] = defaultdict(list)
        self.task_by_key: Dict[tuple, str] = {}
        for t in self.tasks.values():
            self.tasks_by_board[t["board_id"]].append(t["id"])
            self.task_by_key[(t["board_id"], t["title"])] = t["id"]
        self._built = True

    def ready(self) -> "Repository":
        self._build_indexes()
        return self


def _repo(repo: Optional[Repository]) -> Repository:
    return (repo or Repository()).ready()


class UserService(UserBase):
    def __init__(self, repo: Optional[Repository] = None):
        self.repo = _repo(repo)

    def create_user(self, request: str) -> str:
        data = parse(request)
        name = require_str(data, "name", 64)
        display_name = require_str(data, "display_name", 64)
        with storage.LOCK:
            if name in self.repo.user_by_name:
                raise ConflictError(f"user name '{name}' already exists")
            user = {"id": new_id(), "name": name, "display_name": display_name,
                    "creation_time": now()}
            self.repo.users.put(user)
            self.repo.user_by_name[name] = user["id"]
        return dumps({"id": user["id"]})

    def list_users(self) -> str:
        return dumps([{"name": u["name"], "display_name": u["display_name"],
                       "creation_time": u["creation_time"]}
                      for u in self.repo.users.values()])

    def describe_user(self, request: str) -> str:
        user = require_found(self.repo.users.get(parse(request).get("id")), "user",
                             parse(request).get("id"))
        # The spec asks for a "description"; the display name is the only
        # descriptive text a user has, so it is returned under that key.
        return dumps({"name": user["name"], "description": user["display_name"],
                      "creation_time": user["creation_time"]})

    def update_user(self, request: str) -> str:
        data = parse(request)
        user = require_found(self.repo.users.get(data.get("id")), "user", data.get("id"))
        changes = data.get("user")
        if not isinstance(changes, dict):
            raise ValidationError("'user' must be an object")
        name = require_str(changes, "name", 64, required=False)
        display_name = require_str(changes, "display_name", 128, required=False)
        if name is not None and name != user["name"]:
            raise ValidationError("user name cannot be updated")
        with storage.LOCK:
            if display_name is not None:
                user["display_name"] = display_name
            self.repo.users.put(user)
        return dumps({})

    def get_user_teams(self, request: str) -> str:
        data = parse(request)
        user = require_found(self.repo.users.get(data.get("id")), "user", data.get("id"))
        return dumps([{"name": t["name"], "description": t["description"],
                       "creation_time": t["creation_time"]}
                      for t in self.repo.teams.values() if user["id"] in t["users"]])


class TeamService(TeamBase):
    def __init__(self, repo: Optional[Repository] = None):
        self.repo = _repo(repo)

    def _team(self, data: dict) -> dict:
        return require_found(self.repo.teams.get(data.get("id")), "team", data.get("id"))

    def _user_ids(self, data: dict) -> List[str]:
        users = data.get("users")
        if not isinstance(users, list) or not users:
            raise ValidationError("'users' must be a non-empty list of user ids")
        if len(users) > MAX_TEAM_USERS:
            raise ValidationError(f"at most {MAX_TEAM_USERS} users per request")
        if not all(isinstance(u, str) for u in users):
            raise ValidationError("user ids must be strings")
        for uid in users:
            require_found(self.repo.users.get(uid), "user", uid)
        return list(dict.fromkeys(users))  # de-duplicate, keep order

    def create_team(self, request: str) -> str:
        data = parse(request)
        name = require_str(data, "name", 64)
        description = require_str(data, "description", 128, allow_empty=True)
        admin = data.get("admin")
        require_found(self.repo.users.get(admin), "admin user", admin)
        with storage.LOCK:
            if name in self.repo.team_by_name:
                raise ConflictError(f"team name '{name}' already exists")
            team = {"id": new_id(), "name": name, "description": description,
                    "creation_time": now(), "admin": admin, "users": [admin]}
            self.repo.teams.put(team)
            self.repo.team_by_name[name] = team["id"]
        return dumps({"id": team["id"]})

    @staticmethod
    def _summary(t: dict) -> dict:
        return {"name": t["name"], "description": t["description"],
                "creation_time": t["creation_time"], "admin": t["admin"]}

    def list_teams(self) -> str:
        return dumps([self._summary(t) for t in self.repo.teams.values()])

    def describe_team(self, request: str) -> str:
        return dumps(self._summary(self._team(parse(request))))

    def update_team(self, request: str) -> str:
        data = parse(request)
        team = self._team(data)
        changes = data.get("team")
        if not isinstance(changes, dict):
            raise ValidationError("'team' must be an object")
        name = require_str(changes, "name", 64, required=False)
        description = require_str(changes, "description", 128, required=False,
                                  allow_empty=True)
        admin = changes.get("admin")
        if admin is not None:
            require_found(self.repo.users.get(admin), "admin user", admin)
        with storage.LOCK:
            if name is not None and name != team["name"]:
                if name in self.repo.team_by_name:
                    raise ConflictError(f"team name '{name}' already exists")
                del self.repo.team_by_name[team["name"]]
                self.repo.team_by_name[name] = team["id"]
                team["name"] = name
            if description is not None:
                team["description"] = description
            if admin is not None:
                team["admin"] = admin
                if admin not in team["users"]:
                    if len(team["users"]) >= MAX_TEAM_USERS:
                        raise ValidationError(f"a team can have at most {MAX_TEAM_USERS} users")
                    team["users"].append(admin)
            self.repo.teams.put(team)
        return dumps({})

    def add_users_to_team(self, request: str) -> str:
        data = parse(request)
        team = self._team(data)
        user_ids = self._user_ids(data)
        with storage.LOCK:
            fresh = [u for u in user_ids if u not in team["users"]]
            if len(team["users"]) + len(fresh) > MAX_TEAM_USERS:
                raise ValidationError(f"a team can have at most {MAX_TEAM_USERS} users")
            team["users"].extend(fresh)
            self.repo.teams.put(team)
        return dumps({})

    def remove_users_from_team(self, request: str) -> str:
        data = parse(request)
        team = self._team(data)
        user_ids = self._user_ids(data)
        if team["admin"] in user_ids:
            raise ValidationError("the team admin cannot be removed; change the admin first")
        with storage.LOCK:
            team["users"] = [u for u in team["users"] if u not in user_ids]
            self.repo.teams.put(team)
        return dumps({})

    def list_team_users(self, request: str) -> str:
        team = self._team(parse(request))
        out = []
        for uid in team["users"]:
            u = self.repo.users.get(uid)
            out.append({"id": uid, "name": u["name"], "display_name": u["display_name"]})
        return dumps(out)


class BoardService(ProjectBoardBase):
    def __init__(self, repo: Optional[Repository] = None):
        self.repo = _repo(repo)

    def _board(self, board_id) -> dict:
        return require_found(self.repo.boards.get(board_id), "board", board_id)

    def create_board(self, request: str) -> str:
        data = parse(request)
        name = require_str(data, "name", 64)
        description = require_str(data, "description", 128, allow_empty=True)
        team_id = data.get("team_id")
        require_found(self.repo.teams.get(team_id), "team", team_id)
        created = check_timestamp(data.get("creation_time"), "creation_time")
        with storage.LOCK:
            if (team_id, name) in self.repo.board_by_key:
                raise ConflictError(f"board '{name}' already exists for this team")
            board = {"id": new_id(), "name": name, "description": description,
                     "team_id": team_id, "creation_time": created,
                     "status": "OPEN", "end_time": None}
            self.repo.boards.put(board)
            self.repo.board_by_key[(team_id, name)] = board["id"]
        return dumps({"id": board["id"]})

    def close_board(self, request: str) -> str:
        board = self._board(parse(request).get("id"))
        with storage.LOCK:
            if board["status"] == "CLOSED":
                raise ConflictError("board is already closed")
            pending = [tid for tid in self.repo.tasks_by_board[board["id"]]
                       if self.repo.tasks.get(tid)["status"] != "COMPLETE"]
            if pending:
                raise ConflictError(
                    f"cannot close board: {len(pending)} task(s) are not COMPLETE")
            board["status"] = "CLOSED"
            board["end_time"] = now()
            self.repo.boards.put(board)
        return dumps({})

    def add_task(self, request: str) -> str:
        data = parse(request)
        board = self._board(data.get("board_id"))
        title = require_str(data, "title", 64)
        description = require_str(data, "description", 128, allow_empty=True)
        user_id = data.get("user_id")
        user = require_found(self.repo.users.get(user_id), "user", user_id)
        team = self.repo.teams.get(board["team_id"])
        if user["id"] not in team["users"]:
            raise ValidationError("task can only be assigned to a member of the board's team")
        created = check_timestamp(data.get("creation_time"), "creation_time")
        with storage.LOCK:
            if board["status"] != "OPEN":
                raise ConflictError("tasks can only be added to an OPEN board")
            if (board["id"], title) in self.repo.task_by_key:
                raise ConflictError(f"task '{title}' already exists on this board")
            task = {"id": new_id(), "board_id": board["id"], "title": title,
                    "description": description, "user_id": user_id,
                    "creation_time": created, "status": "OPEN"}
            self.repo.tasks.put(task)
            self.repo.tasks_by_board[board["id"]].append(task["id"])
            self.repo.task_by_key[(board["id"], title)] = task["id"]
        return dumps({"id": task["id"]})

    def update_task_status(self, request: str) -> str:
        data = parse(request)
        task = require_found(self.repo.tasks.get(data.get("id")), "task", data.get("id"))
        status = data.get("status")
        if status not in TASK_STATUSES:
            raise ValidationError(f"'status' must be one of {', '.join(TASK_STATUSES)}")
        with storage.LOCK:
            if self._board(task["board_id"])["status"] == "CLOSED":
                raise ConflictError("cannot change tasks of a CLOSED board")
            task["status"] = status
            self.repo.tasks.put(task)
        return dumps({})

    def list_boards(self, request: str) -> str:
        team_id = parse(request).get("id")
        require_found(self.repo.teams.get(team_id), "team", team_id)
        return dumps([{"id": b["id"], "name": b["name"]}
                      for b in self.repo.boards.values()
                      if b["team_id"] == team_id and b["status"] == "OPEN"])

    def export_board(self, request: str) -> str:
        board = self._board(parse(request).get("id"))
        team = self.repo.teams.get(board["team_id"])
        tasks = [self.repo.tasks.get(t) for t in self.repo.tasks_by_board[board["id"]]]
        lines = render_board(board, team, tasks, self.repo.users)
        os.makedirs(self.repo.out_dir, exist_ok=True)
        file_name = f"board_{board['id']}.txt"
        with open(os.path.join(self.repo.out_dir, file_name), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        return dumps({"out_file": file_name})


def render_board(board: dict, team: dict, tasks: List[dict], users) -> List[str]:
    """Plain-text kanban view: header, progress bar, then one column per status."""
    width = 64
    done = sum(t["status"] == "COMPLETE" for t in tasks)
    pct = round(100 * done / len(tasks)) if tasks else 0
    bar = "#" * (pct * 30 // 100) + "-" * (30 - pct * 30 // 100)
    lines = ["=" * width, f" BOARD: {board['name']}".ljust(width - 10) + f"[{board['status']}]",
             "=" * width,
             f" Team        : {team['name']}",
             f" Description : {board['description'] or '-'}",
             f" Created     : {board['creation_time']}",
             f" Closed      : {board['end_time'] or '-'}",
             f" Progress    : [{bar}] {pct}% ({done}/{len(tasks)} complete)", ""]
    for status in TASK_STATUSES:
        column = [t for t in tasks if t["status"] == status]
        lines.append(f"-- {status.replace('_', ' ')} ({len(column)}) ".ljust(width, "-"))
        for t in column:
            owner = users.get(t["user_id"])["display_name"]
            lines.append(f"  * {t['title']}  (assignee: {owner})")
            if t["description"]:
                lines.append(f"      {t['description']}")
        if not column:
            lines.append("  (none)")
        lines.append("")
    return lines
