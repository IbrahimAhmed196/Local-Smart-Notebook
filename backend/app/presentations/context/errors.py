"""Errors of the context step. They derive from RuntimeError, like the LLM errors, so existing handlers still work."""
 
 
class ContextError(RuntimeError):
    """The context could not be built. The message is written for the user and shown as it is."""
 
 
class ContextTooLargeError(ContextError):
    """Too many documents, or a document over the size limit (CTX-03). Raised before any model call."""
 
 
class ContextExtractionError(ContextError):
    """The model could not give usable facts for one document after the client's retries (CTX-04)."""
