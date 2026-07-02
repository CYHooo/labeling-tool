# annotation_tool/main.py
"""Entry point for the ConcJoint annotation tool."""
import sys
import argparse

from PyQt5.QtWidgets import QApplication

from annotation_tool.ui.main_window import MainWindow


def main():
    parser = argparse.ArgumentParser(description="ConcJoint semi-auto annotator")
    parser.add_argument("--dataset", default=None,
                        help="dataset dir containing images/ and masks/ "
                             "(optional; you can also pick one via File > Open Folder)")
    parser.add_argument("--backend", default=None, choices=[None, "sam2", "sam3"],
                        help="override configs.BACKEND")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    win = MainWindow(dataset_dir=args.dataset, backend=args.backend)
    win.showMaximized()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
