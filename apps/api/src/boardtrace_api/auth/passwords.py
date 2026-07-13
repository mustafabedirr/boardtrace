from importlib import import_module
from typing import Protocol, cast


class _PasswordHash(Protocol):
    @classmethod
    def recommended(cls) -> "_PasswordHash": ...

    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...


PasswordHash = cast(type[_PasswordHash], import_module("pwdlib").PasswordHash)


class PasswordService:
    def __init__(self) -> None:
        self._hasher = PasswordHash.recommended()
        self._dummy_hash = self._hasher.hash("boardtrace-dummy-password")

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        return self._hasher.verify(password, password_hash)

    def dummy_verify(self, password: str) -> None:
        self._hasher.verify(password, self._dummy_hash)
