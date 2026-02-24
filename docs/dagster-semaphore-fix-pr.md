# Fix semaphore leak in `start_termination_thread`

## Summary

`start_termination_thread()` in `dagster/_utils/__init__.py` unnecessarily instantiates a `multiprocessing.Event()` on every call, just to pass its type to `check.inst_param`. Each instantiation allocates 3 POSIX named semaphores under the hood. Because this function runs in every multiprocess executor child process, the leaked semaphores accumulate and can exhaust the system semaphore limit — causing `OSError: [Errno 28] No space left on device` on macOS under moderate concurrency.

This PR replaces the runtime instantiation with a direct class reference, eliminating the semaphore leak entirely.

**This is not a breaking change.** The fix is purely internal — the runtime behavior of `check.inst_param` is identical (same `isinstance` check, same type), only the way the type argument is obtained changes.

## The problem

```python
# Before (line ~374)
check.inst_param(should_stop_event, "should_stop_event", ttype=type(multiprocessing.Event()))
```

`type(multiprocessing.Event())` calls `multiprocessing.Event()` to get its type. That call creates a real `Event` object, which internally allocates:

- 1 `multiprocessing.Lock` (1 POSIX semaphore)
- 1 `multiprocessing.Condition` (1 `Lock` + 1 `Semaphore` = 2 more POSIX semaphores)

**Total: 3 POSIX named semaphores created and never used**, per child process.

### Impact

`start_termination_thread` is called from `MultiprocessExecutorChildProcessCommand.execute()` in every child worker process. With the multiprocess executor running many concurrent ops, each child leaks 3 semaphores. On macOS, the default POSIX semaphore limit is 10,000 (`kern.posix.sem.max`). A pipeline with enough concurrent steps can exhaust this limit, causing runs to fail with:

```
OSError: [Errno 28] No space left on device
```

This error is misleading — it is not a disk space issue, but kernel semaphore exhaustion.

### Related issues

- [#18728](https://github.com/dagster-io/dagster/issues/18728) — "Ctrl+C can cause hang" (same `start_termination_thread` code path, different symptom, closed as stale)
- [#19149](https://github.com/dagster-io/dagster/issues/19149) — "child process terminated by signal 6 (SIGABRT)" on macOS (11 upvotes, closed as stale)

## The fix

```python
# After
import multiprocessing.synchronize  # added import

check.inst_param(
    should_stop_event, "should_stop_event", ttype=multiprocessing.synchronize.Event
)
```

Two changes:

1. **Add `import multiprocessing.synchronize`** — plain `import multiprocessing` does not auto-import the `synchronize` submodule, so the class is not accessible without the explicit import.
2. **Replace `type(multiprocessing.Event())` with `multiprocessing.synchronize.Event`** — references the class directly, no instantiation, no semaphores allocated.

### Why not `multiprocessing.Event`?

`multiprocessing.Event` is a **bound method** on the default context object, not a class:

```python
>>> import multiprocessing
>>> multiprocessing.Event
<bound method BaseContext.Event of <multiprocessing.context.DefaultContext object at 0x...>>
>>> type(multiprocessing.Event)
<class 'method'>
```

Passing it to `isinstance()` (which is what `check.inst_param` does) would raise `TypeError`. The actual class is `multiprocessing.synchronize.Event`.

## Test plan

- [x] Verified `isinstance(multiprocessing.Event(), multiprocessing.synchronize.Event)` returns `True`
- [x] Verified `check.inst_param(event, "event", ttype=multiprocessing.synchronize.Event)` passes
- [x] Verified `start_termination_thread()` works end-to-end with the patched code
- [x] Ruff lint and format pass with project config (`ruff==0.15.0`, line width 100)
- [ ] Existing dagster test suite (no new tests needed — this is a strict no-behavior-change fix to the type-check argument)
