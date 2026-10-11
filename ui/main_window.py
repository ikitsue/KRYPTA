"""Fenêtre principale et vues de l’application Ciphera."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.models import SubstitutionKey
from core.operations import transform
from core.substitution import SubstitutionError
from crypto.aes_gcm import CipheraCryptoError, MAX_MESSAGE_BYTES
from storage.database import Database, StorageError
from storage.key_io import KeyFileError, load_key, save_key
from ui.key_dialog import KeyDialog
from ui.workers import TransformWorker

logger = logging.getLogger(__name__)
MAX_EDITOR_CHARS = 2 * MAX_MESSAGE_BYTES

APP_STYLE = """
QWidget { background: #11151d; color: #e7eaf0; font-family: "Segoe UI"; font-size: 10pt; }
QMainWindow { background: #11151d; }
QFrame#sidebar { background: #171d28; border-right: 1px solid #283243; }
QLabel#brand { color: #8c9eff; font-size: 21pt; font-weight: 700; }
QLabel#muted { color: #9ba7ba; }
QPushButton {
    background: #202938; border: 1px solid #303d52; border-radius: 8px;
    padding: 9px 13px; color: #e7eaf0;
}
QPushButton:hover { background: #2b3850; border-color: #7188db; }
QPushButton:checked { background: #33416a; border-color: #8297ff; }
QPushButton#primary { background: #6379e8; border: 0; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #788cff; }
QLineEdit, QComboBox, QTextEdit, QTableWidget {
    background: #181f2b; border: 1px solid #303d52; border-radius: 7px;
    padding: 8px; selection-background-color: #5269c8;
}
QComboBox QAbstractItemView { background: #202938; selection-background-color: #5269c8; }
QTableWidget { gridline-color: #303d52; }
QHeaderView::section { background: #202938; padding: 8px; border: 0; }
QProgressBar { border: 0; background: #202938; border-radius: 3px; max-height: 6px; }
QProgressBar::chunk { background: #7c8eff; border-radius: 3px; }
QCheckBox { spacing: 8px; }
"""


class MainWindow(QMainWindow):
    def __init__(self, database: Database | None = None) -> None:
        super().__init__()
        self.database = database or Database()
        self.thread_pool = QThreadPool.globalInstance()
        self.keys: list[SubstitutionKey] = []
        self._worker: TransformWorker | None = None
        self.setWindowTitle("Ciphera — codage et chiffrement local")
        self.resize(1280, 820)
        self.setMinimumSize(940, 640)
        self.setStyleSheet(APP_STYLE)
        self._build_layout()
        self._reload_keys()
        self._refresh_history()
        self._show_page(0)

    def _build_layout(self) -> None:
        root = QWidget()
        horizontal = QHBoxLayout(root)
        horizontal.setContentsMargins(0, 0, 0, 0)
        horizontal.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(218)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(18, 24, 18, 20)
        brand = QLabel("Ciphera")
        brand.setObjectName("brand")
        side_layout.addWidget(brand)
        tagline = QLabel("Vos textes, en local")
        tagline.setObjectName("muted")
        side_layout.addWidget(tagline)
        side_layout.addSpacing(28)
        self.nav_buttons: list[QPushButton] = []
        for index, label in enumerate(
            ("⌂   Accueil", "⇄   Coder / Décoder", "⚿   Mes clés", "◷   Historique", "⚙   Paramètres")
        ):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setToolTip(f"Ouvrir {label.split()[-1]}")
            button.clicked.connect(lambda _checked=False, page=index: self._show_page(page))
            side_layout.addWidget(button)
            self.nav_buttons.append(button)
        side_layout.addStretch(1)
        side_layout.addWidget(QLabel("AES-256-GCM · stockage local"))
        horizontal.addWidget(sidebar)

        self.pages = QStackedWidget()
        horizontal.addWidget(self.pages, 1)
        self.setCentralWidget(root)
        self.pages.addWidget(self._home_page())
        self.pages.addWidget(self._editor_page())
        self.pages.addWidget(self._keys_page())
        self.pages.addWidget(self._history_page())
        self.pages.addWidget(self._settings_page())
        self._install_shortcuts()

    def _page_shell(self, title: str, subtitle: str = "") -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(34, 30, 34, 30)
        layout.setSpacing(18)
        heading = QLabel(title)
        heading.setStyleSheet("font-size: 22pt; font-weight: 650;")
        layout.addWidget(heading)
        if subtitle:
            label = QLabel(subtitle)
            label.setObjectName("muted")
            label.setWordWrap(True)
            layout.addWidget(label)
        return page, layout

    def _home_page(self) -> QWidget:
        page, layout = self._page_shell(
            "Bienvenue dans Ciphera",
            "Codez avec vos propres correspondances ou protégez vos textes avec un chiffrement authentifié. "
            "Tout fonctionne sur cet ordinateur, sans compte ni serveur.",
        )
        cards = QHBoxLayout()
        for title, body in (
            ("Substitution", "Personnalisez vos correspondances. Ce codage n’est pas un chiffrement sécurisé."),
            ("AES-256-GCM", "Chiffrement authentifié avec mot de passe et dérivation Scrypt."),
            ("Local et privé", "Les messages ne sont jamais ajoutés à l’historique."),
        ):
            card = QFrame()
            card.setStyleSheet("QFrame { background:#181f2b; border:1px solid #303d52; border-radius:12px; }")
            card_layout = QVBoxLayout(card)
            title_label = QLabel(title)
            title_label.setStyleSheet("font-size: 14pt; font-weight:600; color:#aebaff;")
            description = QLabel(body)
            description.setWordWrap(True)
            description.setObjectName("muted")
            card_layout.addWidget(title_label)
            card_layout.addWidget(description)
            cards.addWidget(card)
        layout.addLayout(cards)
        start = QPushButton("Ouvrir l’éditeur")
        start.setObjectName("primary")
        start.clicked.connect(lambda: self._show_page(1))
        layout.addWidget(start, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        return page

    def _editor_page(self) -> QWidget:
        page, layout = self._page_shell("Coder / Décoder", "Les transformations sont exécutées en arrière-plan.")
        controls = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItems(("Substitution", "Chiffrement AES-256-GCM"))
        self.action = QComboBox()
        self.action.addItems(("Coder", "Décoder"))
        self.key_selector = QComboBox()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Saisir le mot de passe")
        self.password.setToolTip("Le mot de passe n’est pas enregistré. Sa perte peut rendre les données irrécupérables.")
        controls.addRow("Mode", self.mode)
        controls.addRow("Action", self.action)
        controls.addRow("Clé de substitution", self.key_selector)
        controls.addRow("Mot de passe (jamais stocké)", self.password)
        layout.addLayout(controls)
        self.combined = QCheckBox("Appliquer la substitution à la représentation du message chiffré")
        self.combined.setToolTip("Cette couche modifie uniquement la présentation et n’ajoute aucune sécurité.")
        layout.addWidget(self.combined)
        warning = QLabel(
            "La substitution ne protège pas contre une attaque cryptographique. "
            "Pour un chiffrement, utilisez AES-GCM. Perdre le mot de passe peut rendre les données irrécupérables."
        )
        warning.setObjectName("muted")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        toolbar = QHBoxLayout()
        self.run_button = QPushButton("Lancer  ·  Ctrl+Entrée")
        self.run_button.setObjectName("primary")
        self.reverse_button = QPushButton("⇄ Inverser")
        self.paste_button = QPushButton("Coller")
        self.copy_button = QPushButton("Copier le résultat")
        self.clear_button = QPushButton("Effacer")
        self.import_button = QPushButton("Importer")
        self.export_button = QPushButton("Exporter")
        for button in (
            self.run_button,
            self.reverse_button,
            self.paste_button,
            self.copy_button,
            self.clear_button,
            self.import_button,
            self.export_button,
        ):
            toolbar.addWidget(button)
        layout.addLayout(toolbar)
        editors = QHBoxLayout()
        self.source = QTextEdit()
        self.source.setPlaceholderText("Texte source…")
        self.source.setAcceptRichText(False)
        self.result = QTextEdit()
        self.result.setPlaceholderText("Résultat…")
        self.result.setAcceptRichText(False)
        self.result.setReadOnly(True)
        editors.addWidget(self._editor_panel("TEXTE SOURCE", self.source), 1)
        editors.addWidget(self._editor_panel("RÉSULTAT", self.result), 1)
        layout.addLayout(editors, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.status = QLabel("Prêt.")
        self.status.setObjectName("muted")
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        self.run_button.clicked.connect(self._run_transform)
        self.reverse_button.clicked.connect(self._reverse_panels)
        self.paste_button.clicked.connect(lambda: self.source.setPlainText(self._clipboard_text()))
        self.copy_button.clicked.connect(lambda: self._copy_result())
        self.clear_button.clicked.connect(self._clear_editors)
        self.import_button.clicked.connect(self._import_text)
        self.export_button.clicked.connect(self._export_text)
        self.mode.currentIndexChanged.connect(self._update_editor_controls)
        self.combined.toggled.connect(self._update_editor_controls)
        self._update_editor_controls()
        return page

    def _editor_panel(self, title: str, editor: QTextEdit) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(title)
        label.setObjectName("muted")
        layout.addWidget(label)
        layout.addWidget(editor, 1)
        return panel

    def _keys_page(self) -> QWidget:
        page, layout = self._page_shell(
            "Mes clés",
            "Les clés personnalisées sont enregistrées dans la base locale. Les fichiers JSON importés "
            "sont validés et ne sont jamais exécutés.",
        )
        actions = QHBoxLayout()
        self.key_search = QLineEdit()
        self.key_search.setPlaceholderText("Rechercher une clé…")
        actions.addWidget(self.key_search, 1)
        self.key_add = QPushButton("Créer")
        self.key_edit = QPushButton("Modifier")
        self.key_duplicate = QPushButton("Dupliquer")
        self.key_delete = QPushButton("Supprimer")
        self.key_import = QPushButton("Importer JSON")
        self.key_export = QPushButton("Exporter JSON")
        for button in (
            self.key_add,
            self.key_edit,
            self.key_duplicate,
            self.key_delete,
            self.key_import,
            self.key_export,
        ):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.keys_table = QTableWidget(0, 4)
        self.keys_table.setHorizontalHeaderLabels(["Nom", "Correspondances", "Casse", "Réversibilité"])
        self.keys_table.horizontalHeader().setStretchLastSection(True)
        self.keys_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.keys_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.keys_table, 1)
        note = QLabel(
            "Les clés de substitution sont des correspondances de texte, pas des mots de passe ni des clés AES. "
            "La substitution seule n’est pas un chiffrement sécurisé."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.key_search.textChanged.connect(self._filter_keys)
        self.key_add.clicked.connect(self._create_key)
        self.key_edit.clicked.connect(self._edit_key)
        self.key_duplicate.clicked.connect(self._duplicate_key)
        self.key_delete.clicked.connect(self._delete_key)
        self.key_import.clicked.connect(self._import_key)
        self.key_export.clicked.connect(self._export_key)
        self.keys_table.cellDoubleClicked.connect(lambda _row, _column: self._edit_key())
        return page

    def _history_page(self) -> QWidget:
        page, layout = self._page_shell(
            "Historique",
            "L’historique est désactivé par défaut. Lorsqu’il est activé, seuls la date, l’action, le mode "
            "et le nom de clé sont conservés — jamais les messages, mots de passe ou clés cryptographiques.",
        )
        buttons = QHBoxLayout()
        refresh = QPushButton("Actualiser")
        remove = QPushButton("Supprimer la sélection")
        clear = QPushButton("Tout supprimer")
        buttons.addWidget(refresh)
        buttons.addWidget(remove)
        buttons.addWidget(clear)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.history_table = QTableWidget(0, 4)
        self.history_table.setHorizontalHeaderLabels(["Date (UTC)", "Action", "Mode", "Clé"])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.history_table, 1)
        refresh.clicked.connect(self._refresh_history)
        remove.clicked.connect(self._delete_history_item)
        clear.clicked.connect(self._clear_history)
        return page

    def _settings_page(self) -> QWidget:
        page, layout = self._page_shell("Paramètres", "Préférences enregistrées uniquement sur cet ordinateur.")
        self.history_enabled = QCheckBox("Activer l’historique local des opérations")
        self.history_enabled.setChecked(
            self.database.get_preference("history_enabled", "false") == "true"
        )
        self.history_enabled.toggled.connect(self._set_history_enabled)
        layout.addWidget(self.history_enabled)
        details = QLabel(
            "Quand cette option est activée, Ciphera conserve uniquement la date UTC, l’action, "
            "le mode et le nom de la clé. Le contenu des textes, les mots de passe et les clés "
            "cryptographiques ne sont jamais enregistrés."
        )
        details.setObjectName("muted")
        details.setWordWrap(True)
        layout.addWidget(details)
        location = QLabel(f"Base locale : {self.database.path}")
        location.setObjectName("muted")
        location.setWordWrap(True)
        layout.addWidget(location)
        layout.addStretch(1)
        return page

    def _install_shortcuts(self) -> None:
        shortcuts = (
            ("Ctrl+Return", self._run_transform),
            ("Ctrl+Enter", self._run_transform),
            ("Ctrl+Shift+C", self._copy_result),
            ("Ctrl+Shift+V", lambda: self.source.setPlainText(self._clipboard_text())),
            ("Ctrl+L", self._clear_editors),
        )
        self._shortcuts = []
        for sequence, callback in shortcuts:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)

    def _show_page(self, page: int) -> None:
        self.pages.setCurrentIndex(page)
        for index, button in enumerate(self.nav_buttons):
            button.setChecked(index == page)
        if page == 2:
            self._refresh_keys_table()
        elif page == 3:
            self._refresh_history()

    def _selected_key(self) -> SubstitutionKey | None:
        key_id = self.key_selector.currentData()
        return next((key for key in self.keys if key.id == key_id), None)

    def _update_editor_controls(self, *_args) -> None:
        is_crypto = self.mode.currentText() == "Chiffrement AES-256-GCM"
        self.password.setVisible(is_crypto)
        self.password.setEnabled(is_crypto)
        self.combined.setVisible(is_crypto)
        self.key_selector.setEnabled(not is_crypto or self.combined.isChecked())

    def _run_transform(self) -> None:
        if self._worker is not None:
            return
        text = self.source.toPlainText()
        if len(text) > MAX_EDITOR_CHARS:
            self._show_error("Texte trop volumineux", "La limite de traitement est de 1 Mio de caractères.")
            return
        operation = self.action.currentText()
        mode = self.mode.currentText()
        selected_key = self._selected_key()
        key = selected_key if mode == "Substitution" or self.combined.isChecked() else None
        password = self.password.text()
        combined = mode == "Chiffrement AES-256-GCM" and self.combined.isChecked()
        self.result.clear()
        self.progress.show()
        self.run_button.setEnabled(False)
        self.status.setText("Traitement en cours…")
        worker = TransformWorker(
            lambda: transform(text, operation, mode, key, password, combined)
        )
        self._worker = worker
        worker.signals.succeeded.connect(
            lambda result, op=operation, selected=selected_key, current_mode=mode: self._transform_succeeded(
                result, op, current_mode, selected
            )
        )
        worker.signals.failed.connect(self._transform_failed)
        self.thread_pool.start(worker)

    def _transform_succeeded(
        self, output: str, operation: str, mode: str, key: SubstitutionKey | None
    ) -> None:
        self.result.setPlainText(output)
        self._finish_worker("Terminé.")
        try:
            self.database.add_history(operation, mode, key.name if key else "")
        except StorageError as error:
            logger.error("Historique non enregistré (%s).", type(error).__name__)
            self.status.setText(f"{self.status.text()} L’historique n’a pas pu être enregistré.")
        if key and key.case_warning and mode == "Substitution" and operation == "Coder":
            self.status.setText(key.case_warning)

    def _transform_failed(self, message: str) -> None:
        self._finish_worker("Échec du traitement.")
        self._show_error("Transformation impossible", message)

    def _finish_worker(self, message: str) -> None:
        self._worker = None
        self.progress.hide()
        self.run_button.setEnabled(True)
        self.status.setText(message)

    @staticmethod
    def _clipboard_text() -> str:
        from PySide6.QtWidgets import QApplication

        return QApplication.clipboard().text()

    def _copy_result(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.result.toPlainText())
        self.status.setText("Résultat copié.")

    def _clear_editors(self) -> None:
        self.source.clear()
        self.result.clear()
        self.status.setText("Éditeurs effacés.")

    def _reverse_panels(self) -> None:
        source = self.source.toPlainText()
        result = self.result.toPlainText()
        self.source.setPlainText(result)
        self.result.setPlainText(source)

    def _import_text(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importer un texte", "", "Texte (*.txt);;Tous les fichiers (*)")
        if not path:
            return
        try:
            file_path = Path(path)
            if file_path.stat().st_size > 2 * MAX_MESSAGE_BYTES:
                raise OSError("Le fichier dépasse la limite de 2 Mio.")
            self.source.setPlainText(file_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as error:
            self._show_error("Import impossible", str(error))

    def _export_text(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exporter le résultat", "ciphera-resultat.txt", "Texte (*.txt)")
        if not path:
            return
        try:
            Path(path).write_text(self.result.toPlainText(), encoding="utf-8")
            self.status.setText("Fichier exporté.")
        except OSError as error:
            self._show_error("Export impossible", str(error))

    def _reload_keys(self) -> None:
        try:
            self.keys = self.database.list_keys()
            self.key_selector.clear()
            for key in self.keys:
                self.key_selector.addItem(key.name, key.id)
            if hasattr(self, "keys_table"):
                self._refresh_keys_table()
        except StorageError as error:
            self._show_error("Stockage inaccessible", str(error))

    def _refresh_keys_table(self) -> None:
        self.keys_table.setRowCount(0)
        for key in self.keys:
            row = self.keys_table.rowCount()
            self.keys_table.insertRow(row)
            values = (
                key.name,
                str(len(key.mapping)),
                key.case_mode,
                "Oui" if key.is_reversible else "Non — ambiguë ou casse normalisée",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, key.id)
                self.keys_table.setItem(row, column, item)
        self._filter_keys(self.key_search.text())

    def _filter_keys(self, query: str) -> None:
        query = query.casefold()
        for row in range(self.keys_table.rowCount()):
            self.keys_table.setRowHidden(
                row, query not in self.keys_table.item(row, 0).text().casefold()
            )

    def _selected_managed_key(self) -> SubstitutionKey | None:
        row = self.keys_table.currentRow()
        if row < 0:
            return None
        key_id = self.keys_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        return next((key for key in self.keys if key.id == key_id), None)

    def _create_key(self) -> None:
        dialog = KeyDialog(parent=self)
        if dialog.exec():
            self._save_key(dialog.key_value())

    def _edit_key(self) -> None:
        key = self._selected_managed_key()
        if key is None:
            return
        dialog = KeyDialog(key, self)
        if dialog.exec():
            self._save_key(dialog.key_value())

    def _duplicate_key(self) -> None:
        key = self._selected_managed_key()
        if key is None:
            return
        duplicate = SubstitutionKey(
            id=str(uuid4()),
            name=f"{key.name} — copie",
            mapping=dict(key.mapping),
            case_mode=key.case_mode,
            output_format=key.output_format,
            unknown_mode=key.unknown_mode,
        )
        dialog = KeyDialog(duplicate, self)
        if dialog.exec():
            self._save_key(dialog.key_value())

    def _save_key(self, key: SubstitutionKey) -> None:
        try:
            self.database.save_key(key)
            self._reload_keys()
        except StorageError as error:
            self._show_error("Enregistrement impossible", str(error))

    def _delete_key(self) -> None:
        key = self._selected_managed_key()
        if key is None:
            return
        answer = QMessageBox.question(
            self, "Supprimer la clé", f"Supprimer « {key.name} » ?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.database.delete_key(key.id)
            self._reload_keys()
        except StorageError as error:
            self._show_error("Suppression impossible", str(error))

    def _import_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importer une clé", "", "Clé Ciphera (*.json)")
        if not path:
            return
        try:
            key = load_key(path)
            existing_ids = {item.id for item in self.keys}
            if key.id in existing_ids:
                key.id = str(uuid4())
            self.database.save_key(key)
            self._reload_keys()
        except (KeyFileError, StorageError) as error:
            self._show_error("Import de clé impossible", str(error))

    def _export_key(self) -> None:
        key = self._selected_managed_key()
        if key is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter une clé", f"{key.name}.json", "Clé Ciphera (*.json)"
        )
        if not path:
            return
        try:
            save_key(path, key)
        except KeyFileError as error:
            self._show_error("Export de clé impossible", str(error))

    def _refresh_history(self) -> None:
        if not hasattr(self, "history_table"):
            return
        try:
            history = self.database.list_history()
            self.history_table.setRowCount(0)
            for entry in history:
                row = self.history_table.rowCount()
                self.history_table.insertRow(row)
                for column, value in enumerate(
                    (entry["created_at"], entry["operation"], entry["mode"], entry["key_name"])
                ):
                    item = QTableWidgetItem(value)
                    if column == 0:
                        item.setData(Qt.ItemDataRole.UserRole, entry["id"])
                    self.history_table.setItem(row, column, item)
        except StorageError as error:
            self._show_error("Historique inaccessible", str(error))

    def _delete_history_item(self) -> None:
        row = self.history_table.currentRow()
        if row < 0:
            return
        item_id = self.history_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        try:
            self.database.delete_history_item(item_id)
            self._refresh_history()
        except StorageError as error:
            self._show_error("Suppression impossible", str(error))

    def _clear_history(self) -> None:
        answer = QMessageBox.question(self, "Effacer l’historique", "Supprimer toutes les entrées ?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.database.clear_history()
            self._refresh_history()
        except StorageError as error:
            self._show_error("Suppression impossible", str(error))

    def _set_history_enabled(self, enabled: bool) -> None:
        try:
            self.database.set_preference("history_enabled", "true" if enabled else "false")
        except StorageError as error:
            self._show_error("Préférence non enregistrée", str(error))

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)
