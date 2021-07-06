import os
import secrets
import gzip

_open_kws = { "buffering", "encoding", "errors", "newline", "closefd", "opener" }
_gzip_kws = { "compresslevel", "encoding", "errors", "newline" }
_ok_modes = { "rb", "ab", "wb", "xb", "rt", "at", "wt", "xt" }

class _FileEx:

    def __init__(self, path, mode, use_gzip, atomic_write, keep_failed, kwargs):
        self.dst_path = path
        self.open_path = path
        self.keep_failed = keep_failed
        self.atomic_write = False

        if mode not in _ok_modes:
            raise ValueError(f"Invalid mode '{mode}', use t/b suffix for explicit mode")

        if use_gzip and path.endswith(".gz"):
            open_fn = gzip.open
            open_kws = _gzip_kws
        else:
            open_fn = open
            open_kws = _open_kws
        
        open_kwargs = { k: v for k,v in kwargs.items() if k in open_kws }

        if mode.endswith("t") and "encoding" not in open_kwargs:
            open_kwargs["encoding"] = "utf-8"

        if atomic_write and mode in ("wb", "wt"):
            self.atomic_write = True
            # Try to generate random names until we can succesfully open one
            for _ in range(32):
                self.open_path = f"{path}.{secrets.token_hex(4)}.tmp"
                try:
                    self.file = open_fn(self.open_path, mode, **open_kwargs)
                    return
                except:
                    pass

        self.file = open_fn(self.open_path, mode, **open_kwargs)
    
    def __enter__(self):
        return self.file

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self.file.close()

            if exc_type:
                raise RuntimeError("User error, re-raised implicitly")

            if self.atomic_write:
                os.replace(self.open_path, self.dst_path)
        except:
            # Remove the temporary file unless everything succeeded
            if self.atomic_write and not self.keep_failed:
                try: os.remove(self.open_path)
                except: pass

            # Prefer to raise the user exception
            if exc_type: return
            else: raise

def open_ex(path, mode, use_gzip=True, atomic_write=True, keep_failed=False, **kwargs):
    """Safely open a file by atomically renaming a temporary one.

    Most are passed directly to open() except:
        keep_failed: If True, don't delete the temporary file on failure
    """
    return _FileEx(path, mode, use_gzip, atomic_write, keep_failed, kwargs)
