"""서비스 전역 오류 계약."""


class ServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(ServiceError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, 404)
