"""Domain errors. Services raise these; main.py turns them into JSON responses."""


class AppError(Exception):
    status_code = 500

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class InvalidFileError(AppError):
    status_code = 400


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class PayloadTooLargeError(AppError):
    status_code = 413


class UnsupportedFileTypeError(AppError):
    status_code = 415

class GenerationCancelled(Exception):
    """The user cancelled a generation operation."""