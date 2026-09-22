"""Lazily export MainWindow so importing submodules like ``labeling_tool.core.app_paths``
does not drag in PyQt5/cv2/the whole main window (see ``labeling_tool.core.window``).
"""

__all__ = ["MainWindow"]


def __getattr__(name):
    if name == "MainWindow":
        from labeling_tool.core.window import MainWindow
        return MainWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
