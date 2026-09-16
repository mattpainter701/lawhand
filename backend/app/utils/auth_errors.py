"""Sign-in refusals that carry a stable, user-safe code.

JSON callers still receive the usual ``status_code`` and ``detail``. Browser
OAuth routes turn the ``code`` into a ``/login?error=<code>`` redirect so a
person sees a sentence instead of a raw JSON body. The code is the only part
that ever leaves the server in that redirect; ``detail`` never does.
"""

from fastapi import HTTPException


class AuthRefusal(HTTPException):
    """An expected refusal of a sign-in or invitation step."""

    def __init__(self, code: str, status_code: int, detail: str):
        super().__init__(status_code=status_code, detail=detail)
        self.code = code
