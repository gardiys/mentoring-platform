from typing import NoReturn

from fastapi import HTTPException, status


def api_error(status_code: int, code: str, message: str) -> NoReturn:
    raise HTTPException(status_code=status_code, detail={"code": code, "message": message})


def unauthorized(message: str = "Authentication is required") -> NoReturn:
    api_error(status.HTTP_401_UNAUTHORIZED, "unauthorized", message)


def forbidden(message: str = "Access is forbidden") -> NoReturn:
    api_error(status.HTTP_403_FORBIDDEN, "forbidden", message)
