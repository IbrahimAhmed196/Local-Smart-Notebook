"""Errors raised by the JSON language-model layer."""


class LlmError(RuntimeError):
    """Base class for failures to obtain a usable model response."""


class LlmUnavailableError(LlmError):
    """The model server is unavailable or the requested model is missing."""


class LlmTimeoutError(LlmError):
    """The request exceeded its configured timeout."""


class LlmInvalidOutputError(LlmError):
    """The response is invalid JSON or does not match the requested schema."""