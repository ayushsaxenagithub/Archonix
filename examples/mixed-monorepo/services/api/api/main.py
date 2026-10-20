from api import models


def create_app():
    return {"models": models.NAMES}
