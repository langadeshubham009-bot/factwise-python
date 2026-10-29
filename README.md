# Team Project Planner

Django-based planner exposing the `UserBase`, `TeamBase` and `ProjectBoardBase` APIs.

## Layout
| File | Role |
|---|---|
| `planner/services.py` | Concrete `UserService`, `TeamService`, `BoardService` + board text renderer |
| `planner/storage.py` | JSON file persistence in `db/` |
| `planner/common.py`, `exceptions.py` | Request parsing, validation, typed errors |
| `planner/views.py`, `urls.py`, `settings.py` | Django HTTP layer (`POST /<group>/<method>/`) |
| `planner/tests.py` | Unit tests |

## Run
```
pip install -r requirements.txt
python manage.py test planner      # tests
python manage.py runserver         # e.g. POST /users/create/ with the JSON body from the docstring
```
The services can also be used directly, e.g. `UserService().create_user('{"name": ...}')`.

## Design choices
* Services own the logic; Django is a thin adapter. Views pass the raw JSON body to the service and return its JSON string, so the base-class contract (JSON in, JSON out) is kept and the logic is testable without HTTP. Django is used for routing, request handling and the test runner; there is no ORM/DB because the brief requires file storage.
* **Persistence:** one JSON file per collection (`users`, `teams`, `boards`, `tasks`). Each is loaded once into memory and written back atomically (temp file + `os.replace`) under a lock. Lookups by id and by unique name/title use in-memory dict indexes, so they are O(1) instead of scanning.
* **Errors:** `ValidationError` (400), `NotFoundError` (404), `ConflictError` (409); the view turns them into `{"error": ...}`.
* **Export:** `out/board_<id>.txt` is a text kanban: header, progress bar, and OPEN / IN PROGRESS / COMPLETE columns with assignees.

## Assumptions
* `add_task` needs a board but the docstring has no board field, so the request takes an extra **`board_id`**.
* Constraint limits are followed literally, including the differing display-name limits (64 on create, 128 on update).
* User `description` (describe_user) is the user's display name. Updating `name` to a different value is rejected; sending the same name is accepted.
* The team admin is automatically a member and cannot be removed (change admin first). Changing admin adds the new admin as a member.
* "Cap at 50": a team holds at most 50 users, and a single add/remove request may list at most 50.
* Adding an existing member or removing a non-member is a no-op. Duplicate ids in a request are collapsed.
* Tasks can only be assigned to members of the board's team and start as `OPEN`.
* Tasks of a CLOSED board are frozen; closing an already closed board is an error.
* `creation_time` is optional on boards/tasks (ISO-8601); defaults to now (UTC).
* `list_boards` returns only OPEN boards, as its comment says.
* Single-process use is assumed (in-memory cache); there is no auth.
