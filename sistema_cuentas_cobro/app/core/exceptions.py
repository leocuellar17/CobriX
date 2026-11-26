"""Excepciones personalizadas de negocio y manejadores globales para FastAPI."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class AppBaseException(Exception):
    """Excepción base de la aplicación."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        error_code: str = "APP_ERROR",
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


class EntityNotFoundException(AppBaseException):
    """Se lanza cuando no se encuentra un recurso solicitado en la base de datos."""

    def __init__(self, entity: str, identifier: int | str) -> None:
        super().__init__(
            message=f"{entity} con identificador '{identifier}' no fue encontrado.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="ENTITY_NOT_FOUND",
        )


class BusinessRuleException(AppBaseException):
    """Se lanza cuando se viola una regla de negocio del dominio."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        error_code: str = "BUSINESS_RULE_VIOLATION",
    ) -> None:
        super().__init__(
            message=message,
            status_code=status_code,
            error_code=error_code,
        )


class DuplicateEntityException(BusinessRuleException):
    """Se lanza cuando se intenta registrar un valor único ya existente."""

    def __init__(self, entity: str, field: str, value: str) -> None:
        super().__init__(
            message=f"Ya existe un {entity} registrado con {field} '{value}'.",
            status_code=status.HTTP_409_CONFLICT,
            error_code="DUPLICATE_ENTITY",
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Registra los manejadores globales de excepciones en la instancia de FastAPI."""

    @app.exception_handler(AppBaseException)
    async def app_base_exception_handler(
        _request: Request,
        exc: AppBaseException,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.error_code,
                "detail": exc.message,
            },
        )
