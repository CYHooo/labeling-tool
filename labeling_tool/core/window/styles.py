"""Dark theme stylesheet for the main window."""

STYLESHEET = """
        QMainWindow, QDialog, QWidget#sidePanel {
            background-color: #1f2329;
            color: #e0e0e0;
        }
        QLabel { color: #e0e0e0; }
        QFrame#loadingBox {
            background-color: #181b20;
            border: 1px solid #2c313a;
            border-radius: 6px;
        }
        QLabel#loadingDetail {
            color: #9ea3aa;
            font-size: 11px;
        }
        QLabel#hintText {
            color: #9ea3aa;
            font-size: 10px;
            font-family: monospace;
            background-color: #181b20;
            border: 1px solid #2c313a;
            border-radius: 4px;
            padding: 6px 8px;
        }
        QGroupBox {
            border: 1px solid #2c313a;
            border-radius: 6px;
            margin-top: 10px;
            padding-top: 6px;
            font-weight: 600;
            color: #d0d4dc;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 10px;
            padding: 0 4px;
            background-color: #1f2329;
        }
        QPushButton {
            background-color: #2d333d;
            color: #e0e0e0;
            border: 1px solid #3a4048;
            border-radius: 4px;
            padding: 6px 10px;
            min-height: 24px;
        }
        QPushButton:hover  { background-color: #3a4048; }
        QPushButton:pressed{ background-color: #252a32; }
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
        QPushButton#primaryAction:hover { background-color: #3b7be8; }
        QPushButton#primaryAction:pressed { background-color: #2257bd; }
        QPushButton#catCrack:checked {
            background-color: #c75450;
            border-color: #c75450;
            color: #ffffff;
            font-weight: 600;
        }
        QPushButton#catSpalling:checked {
            background-color: #3aa55a;
            border-color: #3aa55a;
            color: #ffffff;
            font-weight: 600;
        }
        QComboBox, QSpinBox, QLineEdit {
            background-color: #2d333d;
            color: #e0e0e0;
            border: 1px solid #3a4048;
            border-radius: 4px;
            padding: 3px 6px;
            min-height: 22px;
        }
        QComboBox:disabled, QSpinBox:disabled, QLineEdit:disabled {
            color: #5a5f66;
            background-color: #232830;
            border-color: #2c313a;
        }
        QCheckBox { color: #e0e0e0; spacing: 6px; padding: 2px 0; }
        QRadioButton { color: #e0e0e0; spacing: 6px; padding: 2px 0; }
        QRadioButton:disabled, QCheckBox:disabled { color: #5a5f66; }
        QRadioButton::indicator {
            width: 14px; height: 14px;
            border: 1px solid #5a6270;
            border-radius: 8px;
            background-color: #2d333d;
        }
        QRadioButton::indicator:hover { border-color: #8a929e; }
        QRadioButton::indicator:checked {
            border: 1px solid #2d6cdf;
            background-color: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                stop:0 #ffffff, stop:0.38 #ffffff, stop:0.45 #2d6cdf, stop:1 #2d6cdf);
        }
        QCheckBox::indicator {
            width: 16px; height: 16px;
            border: 1px solid #3a4048;
            border-radius: 3px;
            background-color: #2d333d;
        }
        QCheckBox::indicator:hover { border-color: #5a6270; }
        QCheckBox::indicator:checked {
            background-color: #2d6cdf;
            border-color: #2d6cdf;
            image: none;
        }
        QCheckBox::indicator:checked:hover { background-color: #3b7be8; }
        QComboBox QAbstractItemView {
            background-color: #2d333d;
            color: #e0e0e0;
            selection-background-color: #2d6cdf;
            border: 1px solid #3a4048;
        }
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
        QSlider::groove:horizontal {
            height: 4px;
            background: #2c313a;
            border-radius: 2px;
        }
        QSlider::handle:horizontal {
            background: #2d6cdf;
            width: 14px;
            margin: -5px 0;
            border-radius: 7px;
        }
        QSlider::handle:horizontal:hover { background: #3b7be8; }
        QStatusBar {
            background-color: #181b20;
            color: #9ea3aa;
            border-top: 1px solid #2c313a;
        }
        QProgressBar#uploadProgress {
            background-color: #181b20;
            border: 1px solid #2c313a;
            border-radius: 4px;
            text-align: center;
            color: #e0e0e0;
            min-height: 18px;
        }
        QProgressBar#uploadProgress::chunk {
            background-color: #2d6cdf;
            border-radius: 3px;
        }
        QScrollBar:vertical {
            background: #1f2329;
            width: 10px;
        }
        QScrollBar::handle:vertical {
            background: #3a4048;
            border-radius: 4px;
            min-height: 30px;
        }
        QScrollBar::handle:vertical:hover { background: #4a5160; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QSplitter::handle { background-color: #2c313a; width: 2px; }
        QPushButton#measureToggle:checked {
            background-color: #b8862b;
            border-color: #b8862b;
            color: #ffffff;
            font-weight: 600;
        }
        QPushButton#measureToggle:checked:hover { background-color: #cc972f; }
        QPushButton#toolButton { text-align: left; padding: 6px 10px; }
        QPushButton#toolButton:checked {
            background-color: #2d6cdf;
            border-color: #2d6cdf;
            color: #ffffff;
        }
        QPushButton#toolButton:checked:hover { background-color: #3b7be8; }
        QLabel#toolTitle { color: #e0e0e0; font-weight: 600; }
        QLabel#toolHint { color: #9ea3aa; }
        QFrame#toolRule { color: #3a4048; }
        QLabel#scaleLabel {
            color: #66d9e8;
            font-size: 13px;
            font-weight: 600;
            font-family: monospace;
            padding: 6px 8px;
            background-color: #181b20;
            border: 1px solid #2c4e58;
            border-radius: 4px;
        }
        /* login screen tool tabs: without these the pane falls back to the
           light native palette and the light label text becomes unreadable */
        QTabWidget::pane {
            background-color: #1f2329;
            border: 1px solid #3a4048;
            border-radius: 4px;
            top: -1px;
        }
        QTabWidget > QWidget, QTabWidget QStackedWidget > QWidget {
            background-color: #1f2329;
        }
        QTabBar::tab {
            background-color: #181b20;
            color: #9ea3aa;
            border: 1px solid #3a4048;
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            padding: 6px 14px;
            margin-right: 2px;
        }
        QTabBar::tab:selected {
            background-color: #1f2329;
            color: #f0f0f0;
            border-bottom: 2px solid #2d6cdf;
        }
        QTabBar::tab:hover:!selected { background-color: #2d333d; color: #e0e0e0; }
        /* login screen job list (로컬 작업), matching the QListWidget palette */
        QTableWidget {
            background-color: #181b20;
            alternate-background-color: #1c2026;
            color: #d0d4dc;
            gridline-color: #2c313a;
            border: 1px solid #2c313a;
            border-radius: 4px;
        }
        QTableWidget::item { padding: 3px 6px; }
        QTableWidget::item:selected { background-color: #2d6cdf; color: #ffffff; }
        QHeaderView::section {
            background-color: #232830;
            color: #9ea3aa;
            border: none;
            border-right: 1px solid #2c313a;
            border-bottom: 1px solid #3a4048;
            padding: 4px 6px;
        }
        QTableCornerButton::section { background-color: #232830; border: none; }
        """
