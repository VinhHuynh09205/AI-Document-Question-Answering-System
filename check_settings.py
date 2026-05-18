from app.core.config import get_settings
settings = get_settings()
for attr in dir(settings):
    if not attr.startswith("_"):
        print(f"{attr}: {getattr(settings, attr)}")
