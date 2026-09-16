import sqlite3

MAX_MESSAGE_LENGTH = 140


class SpiderError(Exception):
    pass


class CaptureError(SpiderError):
    def __init__(self, reason: str, message: str):
        self.reason = reason
        super().__init__(message)


class ImageDecodeError(SpiderError):
    def __init__(self):
        super().__init__("The file is not a supported image")


class EngineError(SpiderError):
    pass


class ImageTooLargeError(SpiderError):
    def __init__(self):
        super().__init__("The image file is too large to open")


def log_error(logger, context: str, error: BaseException):
    if isinstance(error, (SpiderError, OSError)):
        logger.warning("%s: %s", context, error)
    else:
        logger.error("%s", context, exc_info=error)


def _shorten(text):
    text = " ".join(str(text).split())
    return text if len(text) <= MAX_MESSAGE_LENGTH else text[:MAX_MESSAGE_LENGTH - 1] + "…"


def describe_error(error: BaseException) -> str:
    if isinstance(error, SpiderError):
        return _shorten(error)

    if isinstance(error, MemoryError):
        return "The image is too large to process"
    if isinstance(error, sqlite3.Error):
        return _shorten(f"History database error: {error}")
    if isinstance(error, FileNotFoundError):
        return "The image file no longer exists"
    if isinstance(error, PermissionError):
        return "Permission denied while reading the image"
    if isinstance(error, OSError):
        return _shorten(f"Could not read the image: {error.strerror or error}")
    if type(error).__module__.startswith("cv2"):
        return "The image could not be processed"
    return _shorten(f"Unexpected error: {error}" if str(error) else f"Unexpected error ({type(error).__name__})")
