"""Domain exceptions. Each carries the HTTP status the Django layer maps it to."""


class PlannerError(Exception):
    status = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ValidationError(PlannerError):
    """Malformed request or constraint violation."""
    status = 400


class NotFoundError(PlannerError):
    status = 404


class ConflictError(PlannerError):
    """Uniqueness clash or an operation not allowed in the current state."""
    status = 409
