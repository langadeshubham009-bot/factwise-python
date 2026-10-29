"""Thin Django HTTP layer: every API method becomes ``POST /<group>/<method>/`` (list-all endpoints also accept GET).

The request body is passed through untouched as the JSON string the service
methods expect, and the service's JSON string is returned as the response.
"""
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .exceptions import PlannerError
from .services import BoardService, Repository, TeamService, UserService

_repo = Repository()
USERS, TEAMS, BOARDS = UserService(_repo), TeamService(_repo), BoardService(_repo)

# url -> (bound service method, takes_request_body)
ROUTES = {
    "users/create": (USERS.create_user, True),
    "users/list": (USERS.list_users, False),
    "users/describe": (USERS.describe_user, True),
    "users/update": (USERS.update_user, True),
    "users/teams": (USERS.get_user_teams, True),
    "teams/create": (TEAMS.create_team, True),
    "teams/list": (TEAMS.list_teams, False),
    "teams/describe": (TEAMS.describe_team, True),
    "teams/update": (TEAMS.update_team, True),
    "teams/add_users": (TEAMS.add_users_to_team, True),
    "teams/remove_users": (TEAMS.remove_users_from_team, True),
    "teams/users": (TEAMS.list_team_users, True),
    "boards/create": (BOARDS.create_board, True),
    "boards/close": (BOARDS.close_board, True),
    "boards/list": (BOARDS.list_boards, True),
    "boards/export": (BOARDS.export_board, True),
    "tasks/add": (BOARDS.add_task, True),
    "tasks/update_status": (BOARDS.update_task_status, True),
}


def make_view(method, takes_body):
    @csrf_exempt
    @require_http_methods(["POST"] if takes_body else ["GET", "POST"])
    def view(request):
        try:
            result = method(request.body.decode("utf-8")) if takes_body else method()
        except PlannerError as exc:
            return JsonResponse({"error": exc.message}, status=exc.status)
        return HttpResponse(result, content_type="application/json")
    return view
