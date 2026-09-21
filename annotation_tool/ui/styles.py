"""Dark theme stylesheet for the annotation tool.

Palette adapted from the reference labeling-tool, mapped onto this app's
widgets (dock widgets, file list, radio-button class panel, menu, canvas).
"""

STYLESHEET = """
    QMainWindow, QWidget, QDialog {
        background-color: #1f2329;
        color: #e0e0e0;
    }
    QLabel { color: #e0e0e0; }

    /* central canvas */
    QGraphicsView {
        background-color: #181b20;
        border: none;
    }

    /* dock widgets (Images / Classes) */
    QDockWidget {
        color: #d0d4dc;
        font-weight: 600;
        titlebar-close-icon: none;
        titlebar-normal-icon: none;
    }
    QDockWidget::title {
        background-color: #232830;
        padding: 6px 8px;
        border: 1px solid #2c313a;
        border-radius: 4px;
    }

    /* file list */
    QListWidget {
        background-color: #181b20;
        color: #d0d4dc;
        border: 1px solid #2c313a;
        border-radius: 4px;
        padding: 2px;
    }
    QListWidget::item { padding: 4px 6px; }
    QListWidget::item:selected {
        background-color: #2d6cdf;
        color: #ffffff;
    }

    /* class panel radio buttons */
    QRadioButton { color: #e0e0e0; spacing: 6px; padding: 3px 0; }
    QRadioButton::indicator {
        width: 14px; height: 14px;
        border-radius: 7px;
        border: 1px solid #3a4048;
        background-color: #2d333d;
    }
    QRadioButton::indicator:hover { border-color: #5a6270; }
    QRadioButton::indicator:checked {
        background-color: #2d6cdf;
        border-color: #2d6cdf;
    }

    /* buttons */
    QPushButton {
        background-color: #2d333d;
        color: #e0e0e0;
        border: 1px solid #3a4048;
        border-radius: 4px;
        padding: 6px 10px;
        min-height: 24px;
    }
    QPushButton:hover   { background-color: #3a4048; }
    QPushButton:pressed { background-color: #252a32; }
    QPushButton:disabled {
        color: #5a5f66;
        background-color: #232830;
    }
    QPushButton#primaryAction {
        background-color: #2d6cdf;
        border: 1px solid #2d6cdf;
        color: #ffffff;
        font-weight: 600;
    }
    QPushButton#primaryAction:hover   { background-color: #3b7be8; }
    QPushButton#primaryAction:pressed { background-color: #2257bd; }

    /* menu bar */
    QMenuBar { background-color: #181b20; color: #e0e0e0; }
    QMenuBar::item { padding: 4px 10px; background: transparent; }
    QMenuBar::item:selected { background-color: #2d6cdf; color: #ffffff; }
    QMenu {
        background-color: #232830;
        color: #e0e0e0;
        border: 1px solid #2c313a;
    }
    QMenu::item:selected { background-color: #2d6cdf; color: #ffffff; }

    /* status bar */
    QStatusBar {
        background-color: #181b20;
        color: #9ea3aa;
        border-top: 1px solid #2c313a;
    }

    /* scrollbars */
    QScrollBar:vertical { background: #1f2329; width: 10px; }
    QScrollBar::handle:vertical {
        background: #3a4048;
        border-radius: 4px;
        min-height: 30px;
    }
    QScrollBar::handle:vertical:hover { background: #4a5160; }
    QScrollBar:horizontal { background: #1f2329; height: 10px; }
    QScrollBar::handle:horizontal {
        background: #3a4048;
        border-radius: 4px;
        min-width: 30px;
    }
    QScrollBar::handle:horizontal:hover { background: #4a5160; }
    QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
"""
