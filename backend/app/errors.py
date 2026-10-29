from fastapi import HTTPException


class ApiError(HTTPException):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(status_code=status, detail={"code": code, "message": message})


def not_found(what: str = "Order") -> ApiError:
    return ApiError(404, "not_found", f"{what} not found.")
