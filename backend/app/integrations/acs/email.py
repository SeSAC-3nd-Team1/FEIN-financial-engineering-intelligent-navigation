"""Azure Communication Services Email 발송 어댑터."""

from typing import Protocol

from app.core.errors import ServiceError


class VerificationEmailSender(Protocol):
    def send_verification_code(self, recipient: str, code: str, expires_minutes: int) -> None:
        """수신자에게 가입 인증번호를 발송한다."""


class AcsEmailSender:
    """ACS Email SDK를 지연 로드해 인증번호 메일을 발송한다."""

    def __init__(self, connection_string: str, sender_address: str) -> None:
        self.connection_string = connection_string
        self.sender_address = sender_address

    def send_verification_code(self, recipient: str, code: str, expires_minutes: int) -> None:
        try:
            from azure.communication.email import EmailClient
        except ImportError as exc:
            raise ServiceError(
                "EMAIL_PROVIDER_UNAVAILABLE",
                "이메일 발송 모듈을 사용할 수 없습니다.",
                503,
            ) from exc

        message = {
            "senderAddress": self.sender_address,
            "recipients": {"to": [{"address": recipient}]},
            "content": {
                "subject": "[FEIN] 이메일 인증번호 안내",
                "plainText": (
                    f"이메일 인증번호는 {code}입니다. "
                    f"{expires_minutes}분 안에 입력해 주세요."
                ),
                "html": (
                    "<p>FEIN 회원가입 이메일 인증번호입니다.</p>"
                    f"<p style=\"font-size:24px;font-weight:700;letter-spacing:4px\">{code}</p>"
                    f"<p>{expires_minutes}분 안에 입력해 주세요.</p>"
                ),
            },
        }
        try:
            client = EmailClient.from_connection_string(self.connection_string)
            result = client.begin_send(message).result()
            delivery_status = result.get("status")
        except Exception as exc:
            raise ServiceError(
                "EMAIL_DELIVERY_FAILED",
                "인증 이메일을 발송하지 못했습니다. 잠시 후 다시 시도해 주세요.",
                502,
            ) from exc
        if delivery_status != "Succeeded":
            raise ServiceError(
                "EMAIL_DELIVERY_FAILED",
                "인증 이메일을 발송하지 못했습니다. 잠시 후 다시 시도해 주세요.",
                502,
            )
