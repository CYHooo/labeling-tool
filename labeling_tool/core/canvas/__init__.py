"""Lazily export ImageCanvas: importing submodules such as
``labeling_tool.core.canvas.viewport`` must not force-import
``image_canvas`` (which in turn imports ``labeling_tool.core.bbox``,
creating a circular import when bbox is imported first).
"""

__all__ = ["ImageCanvas"]


def __getattr__(name):
    if name == "ImageCanvas":
        from labeling_tool.core.canvas.image_canvas import ImageCanvas
        return ImageCanvas
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
