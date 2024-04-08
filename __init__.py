# Copyright (c) 2020 Jaime van Kessel, Ultimaker B.V.
# The PostProcessingPlugin is released under the terms of the AGPLv3 or higher.

from . import PostProcessingGui


def getMetaData():
    return {}

def register(app):
    return {"extension": PostProcessingGui.PostProcessingGui()}