from typing import Any


class AppError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        error: str,
        message: str,
        details: Any = None,
    ) -> None:
        self.status_code = status_code
        self.error = error
        self.message = message
        self.details = details

        super().__init__(message)
