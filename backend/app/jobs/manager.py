"""Background jobs """
 
import logging
from concurrent.futures import Future, ThreadPoolExecutor
 
log = logging.getLogger(__name__)
 
 
class JobManager:
    def __init__(self, max_workers: int = 1, inline: bool = False):
        self.max_workers = max_workers
        self.inline = inline
        self._pool: ThreadPoolExecutor | None = None
 
    def submit(self, fn, *args, **kwargs) -> Future | None:
        if self.inline:
            self._run(fn, args, kwargs)
            return None
        if self._pool is None:
            self._pool = ThreadPoolExecutor(
                max_workers=self.max_workers, thread_name_prefix="job"
            )
        return self._pool.submit(self._run, fn, args, kwargs)
 
    @staticmethod
    def _run(fn, args, kwargs) -> None:
        try:
            fn(*args, **kwargs)
        except Exception:  # a failing job must never kill the worker thread
            log.exception("Background job %s crashed", getattr(fn, "__name__", fn))
 
    def shutdown(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._pool = None
 
 
job_manager = JobManager()

