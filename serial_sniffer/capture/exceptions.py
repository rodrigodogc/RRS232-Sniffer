"""Exceções específicas da camada de captura serial."""


class SnifferCaptureError(Exception):
    """Base para erros de captura."""


class PortOpenError(SnifferCaptureError):
    """Falha ao abrir uma porta serial."""


class PortBusyError(PortOpenError):
    """A porta serial está ocupada por outro processo."""


class PortDisconnectedError(SnifferCaptureError):
    """A porta serial foi desconectada durante a captura."""


class CaptureAlreadyRunningError(SnifferCaptureError):
    """Uma tentativa de iniciar captura enquanto outra sessão já está ativa."""
