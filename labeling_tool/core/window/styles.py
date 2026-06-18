"""Dark theme stylesheet for the main window."""

STYLESHEET = """
        QMainWindow, QDialog, QWidget#sidePanel {
            background-color: #1f2329;
            color: #e0e0e0;
        }
        QLabel { color: #e0e0e0; }
        QLabel#appTitle {
            font-size: 14px;
            font-weight: bold;
            color: #f0f0f0;
            padding: 4px 0 8px 0;
            border-bottom: 1px solid #3a4048;
        }
        QLabel#pathLabel {
            color: #888c93;
            font-size: 10px;
            padding: 1px 0;
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
        QPushButton#brushToggle:checked {
            background-color: #2d6cdf;
            border-color: #2d6cdf;
            color: #ffffff;
            font-weight: 600;
        }
        QPushButton#brushToggle:checked:hover { background-color: #3b7be8; }
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
        QCheckBox { color: #e0e0e0; spacing: 6px; padding: 2px 0; }
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
        QPushButton#bboxToggle:checked {
            background-color: #c08a35;
            border-color: #c08a35;
            color: #ffffff;
            font-weight: 600;
        }
        QPushButton#bboxToggle:checked:hover { background-color: #d4983a; }
        QPushButton#measureToggle:checked {
            background-color: #b8862b;
            border-color: #b8862b;
            color: #ffffff;
            font-weight: 600;
        }
        QPushButton#measureToggle:checked:hover { background-color: #cc972f; }
        QPushButton#samToggle:checked {
            background-color: #2a9d8f;
            border-color: #2a9d8f;
            color: #ffffff;
            font-weight: 600;
        }
        QPushButton#samToggle:checked:hover { background-color: #33b3a3; }
        QPushButton#showHighlightToggle:checked {
            background-color: #caa42e;
            border-color: #caa42e;
            color: #1f2329;
            font-weight: 600;
        }
        QPushButton#showHighlightToggle:checked:hover { background-color: #d8b341; }
        QPushButton#showRepair15Toggle:checked {
            background-color: #2596be;
            border-color: #2596be;
            color: #ffffff;
            font-weight: 600;
        }
        QPushButton#showRepair15Toggle:checked:hover { background-color: #2ba6d2; }
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
        """
