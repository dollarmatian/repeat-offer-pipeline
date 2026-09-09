from django.apps import AppConfig
from django.conf import settings


class EngineConfig(AppConfig):
    name = "engine"

    def ready(self):
        from engine.registry import registry

        for module_path in settings.RULESETS:
            registry.load(module_path)
