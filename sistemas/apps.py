from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sistemas'

    def ready(self):
        # importa signals para registrar o receiver automaticamente
        try:
            from . import signals  # noqa: F401
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Erro ao importar sinais em ready()")