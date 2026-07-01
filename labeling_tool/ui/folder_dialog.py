"""Startup dialog for the standalone labeler: pick an image folder and a mask
folder (output defaults to a Labeling/ folder beside the image folder)."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFileDialog, QMessageBox,
)

from labeling_tool.session.local_pairing import pair_by_stem


class FolderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("이미지/마스크 폴더 선택")
        self.image_dir: Path | None = None
        self.mask_dir: Path | None = None
        self.output_dir: Path | None = None

        self.ed_img = QLineEdit(); self.ed_img.setReadOnly(True)
        self.ed_msk = QLineEdit(); self.ed_msk.setReadOnly(True)
        self.lbl_count = QLabel("페어: -")
        btn_img = QPushButton("이미지 폴더…"); btn_img.clicked.connect(self._pick_img)
        btn_msk = QPushButton("마스크 폴더…"); btn_msk.clicked.connect(self._pick_msk)
        self.btn_ok = QPushButton("열기"); self.btn_ok.setDefault(True)
        self.btn_ok.setEnabled(False); self.btn_ok.clicked.connect(self._accept)

        root = QVBoxLayout(self)
        for lbl, ed, btn in (("이미지", self.ed_img, btn_img),
                             ("마스크", self.ed_msk, btn_msk)):
            row = QHBoxLayout()
            row.addWidget(QLabel(lbl)); row.addWidget(ed, 1); row.addWidget(btn)
            root.addLayout(row)
        root.addWidget(self.lbl_count)
        root.addWidget(self.btn_ok)

    def _pick_img(self):
        d = QFileDialog.getExistingDirectory(self, "이미지 폴더")
        if d:
            self.set_dirs(d, str(self.mask_dir) if self.mask_dir else None)

    def _pick_msk(self):
        d = QFileDialog.getExistingDirectory(self, "마스크 폴더")
        if d:
            self.set_dirs(str(self.image_dir) if self.image_dir else None, d)

    def set_dirs(self, image_dir, mask_dir):
        """Set image/mask dirs (also the test hook — bypasses native pickers)."""
        if image_dir:
            self.image_dir = Path(image_dir)
            self.ed_img.setText(str(self.image_dir))
            self.output_dir = self.image_dir.parent / "Labeling"
        if mask_dir:
            self.mask_dir = Path(mask_dir)
            self.ed_msk.setText(str(self.mask_dir))
        n = self.paired_count()
        self.lbl_count.setText(f"페어: {n if n is not None else '-'}")
        self.btn_ok.setEnabled(bool(n))

    def paired_count(self):
        if not (self.image_dir and self.mask_dir):
            return None
        return sum(1 for _, m in pair_by_stem(self.image_dir, self.mask_dir)
                   if m is not None)

    def _accept(self):
        if not self.paired_count():
            QMessageBox.warning(self, "없음", "페어되는 이미지/마스크가 없습니다.")
            return
        self.accept()
