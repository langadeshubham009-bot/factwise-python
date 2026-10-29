"""Run with:  python manage.py test planner"""
import json
import os
import shutil
import tempfile
import unittest

from .exceptions import ConflictError, NotFoundError, ValidationError
from .services import BoardService, Repository, TeamService, UserService


def j(**kw):
    return json.dumps(kw)


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = Repository(os.path.join(self.tmp, "db"), os.path.join(self.tmp, "out"))
        self.users, self.teams, self.boards = (
            UserService(self.repo), TeamService(self.repo), BoardService(self.repo))
        self.alice = self.user("alice")
        self.team = json.loads(self.teams.create_team(
            j(name="core", description="d", admin=self.alice)))["id"]

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def user(self, name):
        return json.loads(self.users.create_user(j(name=name, display_name=name.title())))["id"]

    def board(self, name="sprint1"):
        return json.loads(self.boards.create_board(
            j(name=name, description="", team_id=self.team)))["id"]

    def task(self, board, title="t1", user=None):
        return json.loads(self.boards.add_task(
            j(board_id=board, title=title, description="x", user_id=user or self.alice)))["id"]

    # users
    def test_user_constraints(self):
        with self.assertRaises(ConflictError):
            self.users.create_user(j(name="alice", display_name="x"))
        with self.assertRaises(ValidationError):
            self.users.create_user(j(name="n" * 65, display_name="x"))
        with self.assertRaises(ValidationError):
            self.users.create_user("not json")

    def test_user_update_rules(self):
        with self.assertRaises(ValidationError):
            self.users.update_user(j(id=self.alice, user={"name": "bob"}))
        self.users.update_user(j(id=self.alice, user={"display_name": "A" * 128}))
        with self.assertRaises(ValidationError):
            self.users.update_user(j(id=self.alice, user={"display_name": "A" * 129}))
        with self.assertRaises(NotFoundError):
            self.users.describe_user(j(id="nope"))

    # teams
    def test_team_membership(self):
        bob = self.user("bob")
        self.teams.add_users_to_team(j(id=self.team, users=[bob, bob]))
        self.assertEqual(len(json.loads(self.teams.list_team_users(j(id=self.team)))), 2)
        self.assertEqual(len(json.loads(self.users.get_user_teams(j(id=bob)))), 1)
        with self.assertRaises(ValidationError):  # admin can't be removed
            self.teams.remove_users_from_team(j(id=self.team, users=[self.alice]))
        self.teams.remove_users_from_team(j(id=self.team, users=[bob]))
        self.assertEqual(len(json.loads(self.teams.list_team_users(j(id=self.team)))), 1)

    def test_team_cap_and_uniqueness(self):
        ids = [self.user(f"u{i}") for i in range(50)]
        with self.assertRaises(ValidationError):
            self.teams.add_users_to_team(j(id=self.team, users=ids))  # 1 admin + 50
        with self.assertRaises(ConflictError):
            self.teams.create_team(j(name="core", description="", admin=self.alice))
        with self.assertRaises(NotFoundError):
            self.teams.create_team(j(name="x", description="", admin="ghost"))

    # boards & tasks
    def test_board_lifecycle(self):
        b = self.board()
        with self.assertRaises(ConflictError):
            self.board()  # duplicate name in team
        t = self.task(b)
        with self.assertRaises(ConflictError):
            self.task(b)  # duplicate title
        with self.assertRaises(ConflictError):
            self.boards.close_board(j(id=b))  # task not complete
        with self.assertRaises(ValidationError):
            self.boards.update_task_status(j(id=t, status="DONE"))
        self.boards.update_task_status(j(id=t, status="COMPLETE"))
        self.boards.close_board(j(id=b))
        with self.assertRaises(ConflictError):
            self.task(b, "t2")  # closed board
        self.assertEqual(json.loads(self.boards.list_boards(j(id=self.team))), [])

    def test_task_assignee_must_be_team_member(self):
        outsider = self.user("eve")
        with self.assertRaises(ValidationError):
            self.task(self.board(), user=outsider)

    def test_export_and_persistence(self):
        b = self.board()
        t = self.task(b)
        self.boards.update_task_status(j(id=t, status="IN_PROGRESS"))
        name = json.loads(self.boards.export_board(j(id=b)))["out_file"]
        text = open(os.path.join(self.tmp, "out", name)).read()
        self.assertIn("IN PROGRESS (1)", text)
        # a fresh repository over the same files sees the same data
        again = BoardService(Repository(os.path.join(self.tmp, "db"), self.repo.out_dir))
        self.assertEqual(len(json.loads(again.list_boards(j(id=self.team)))), 1)
