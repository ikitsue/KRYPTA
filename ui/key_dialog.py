"""Éditeur visuel de clés de substitution."""

from __future__ import annotations

from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.models import KeyValidationError, SubstitutionKey


class KeyDialog(QDialog):
    def __init__(self, key: SubstitutionKey | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Modifier une clé" if key else "Créer une clé")
        self.resize(720, 560)
        self._key_id = key.id if key else None
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(key.name if key else "Ma clé")
        self.case_mode = QComboBox()
        self.case_mode.addItem("Majuscules et minuscules distinctes", "sensitive")
        self.case_mode.addItem("Correspondance commune (casefold)", "common")
        self.case_mode.addItem("Normaliser en minuscules", "lower")
        self.output_format = QComboBox()
        self.output_format.addItem("Avec séparateurs et échappement", "separated")
        self.output_format.addItem("Compact — code préfixe obligatoire", "compact")
        self.unknown_mode = QComboBox()
        self.unknown_mode.addItem("Échapper et préserver", "preserve")
        self.unknown_mode.addItem("Refuser les inconnus", "error")
        if key:
            self._set_combo(self.case_mode, key.case_mode)
            self._set_combo(self.output_format, key.output_format)
            self._set_combo(self.unknown_mode, key.unknown_mode)
        form.addRow("Nom", self.name)
        form.addRow("Casse", self.case_mode)
        form.addRow("Format de sortie", self.output_format)
        form.addRow("Caractères inconnus", self.unknown_mode)
        layout.addLayout(form)
        layout.addWidget(QLabel(
            "En format compact, les jetons doivent être distincts et former un code préfixe. "
            "Le format séparé échappe « | » et « \\\\ »."
        ))
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher un caractère…")
        add_button = QPushButton("Ajouter")
        edit_button = QPushButton("Modifier")
        remove_button = QPushButton("Supprimer")
        search_row.addWidget(self.search, 1)
        search_row.addWidget(add_button)
        search_row.addWidget(edit_button)
        search_row.addWidget(remove_button)
        layout.addLayout(search_row)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Caractère d’entrée", "Jeton de sortie"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table, 1)
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.preview)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.search.textChanged.connect(self._filter)
        add_button.clicked.connect(self._add)
        edit_button.clicked.connect(self._edit)
        remove_button.clicked.connect(self._remove)
        self.table.itemChanged.connect(lambda _item: self._refresh_preview())
        self.case_mode.currentIndexChanged.connect(self._refresh_preview)
        self.output_format.currentIndexChanged.connect(self._refresh_preview)
        self.unknown_mode.currentIndexChanged.connect(self._refresh_preview)
        self.name.textChanged.connect(self._refresh_preview)
        if key:
            for source, token in key.mapping.items():
                self._append_row(source, token)
        self._refresh_preview()

    @staticmethod
    def _set_combo(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _append_row(self, source: str, token: str) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(source))
        self.table.setItem(row, 1, QTableWidgetItem(token))

    def _selected_row(self) -> int:
        return self.table.currentRow()

    def _add(self) -> None:
        source, ok = QInputDialog.getText(self, "Nouvelle correspondance", "Caractère d’entrée")
        if not ok:
            return
        token, ok = QInputDialog.getText(self, "Nouvelle correspondance", "Jeton de sortie")
        if ok:
            self._append_row(source, token)
            self._refresh_preview()

    def _edit(self) -> None:
        row = self._selected_row()
        if row < 0:
            return
        source = self.table.item(row, 0).text()
        token = self.table.item(row, 1).text()
        new_source, ok = QInputDialog.getText(
            self, "Modifier la correspondance", "Caractère d’entrée", text=source
        )
        if not ok:
            return
        new_token, ok = QInputDialog.getText(
            self, "Modifier la correspondance", "Jeton de sortie", text=token
        )
        if ok:
            self.table.item(row, 0).setText(new_source)
            self.table.item(row, 1).setText(new_token)
            self._refresh_preview()

    def _remove(self) -> None:
        row = self._selected_row()
        if row >= 0:
            self.table.removeRow(row)
            self._refresh_preview()

    def _filter(self, query: str) -> None:
        query = query.casefold()
        for row in range(self.table.rowCount()):
            source = self.table.item(row, 0).text()
            token = self.table.item(row, 1).text()
            self.table.setRowHidden(row, query not in source.casefold() + token.casefold())

    def _build_key(self) -> SubstitutionKey:
        mapping: dict[str, str] = {}
        for row in range(self.table.rowCount()):
            source_item = self.table.item(row, 0)
            token_item = self.table.item(row, 1)
            if source_item is None or token_item is None:
                raise KeyValidationError("Une ligne de correspondance est incomplète.")
            source, token = source_item.text(), token_item.text()
            if source in mapping:
                raise KeyValidationError(f"Le caractère {source!r} apparaît plusieurs fois.")
            mapping[source] = token
        return SubstitutionKey(
            id=self._key_id or str(uuid4()),
            name=self.name.text().strip(),
            mapping=mapping,
            case_mode=self.case_mode.currentData(),
            output_format=self.output_format.currentData(),
            unknown_mode=self.unknown_mode.currentData(),
        )

    def _refresh_preview(self, *_args) -> None:
        try:
            key = self._build_key()
            self.preview.setText(
                "Aperçu : " + ("réversible" if key.is_reversible else "non réversible / casse normalisée")
            )
        except (KeyValidationError, TypeError) as error:
            self.preview.setText(f"Aperçu indisponible : {error}")

    def _accept(self) -> None:
        try:
            self._build_key()
        except (KeyValidationError, TypeError) as error:
            QMessageBox.warning(self, "Clé invalide", str(error))
            return
        self.accept()

    def key_value(self) -> SubstitutionKey:
        return self._build_key()
