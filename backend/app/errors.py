from fastapi import HTTPException


def err(status: int, code: str, message: str) -> HTTPException:
    """All API errors share one shape: {"detail": {"code": ..., "message": ...}}"""
    return HTTPException(status_code=status, detail={"code": code, "message": message})
