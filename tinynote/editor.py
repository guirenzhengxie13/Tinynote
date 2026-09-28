from PySide6.QtCore import QRectF, Qt, Signal, QTextBoundaryFinder
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit


def tail_characters(text, count):
    """Take grapheme clusters, keeping emoji and combining marks intact."""
    finder = QTextBoundaryFinder(QTextBoundaryFinder.BoundaryType.Grapheme, text)
    finder.toEnd()
    start = len(text.encode("utf-16-le")) // 2
    for _ in range(count):
        previous = finder.toPreviousBoundary()
        if previous < 0:
            start = 0
            break
        start = previous
    return text.encode("utf-16-le")[start * 2:].decode("utf-16-le")


class HiddenEditor(QPlainTextEdit):
    ime_committed = Signal()
    composition_changed = Signal(bool)
    mode_changed = Signal(bool)

    def __init__(self, parent=None, context_chars=4):
        super().__init__(parent)
        self.context_chars = context_chars
        self.revealed = False
        self.preedit = ""
        self.composing = False
        self.in_ime_event = False
        self.dispatch = lambda sequence: False
        self.setFrameShape(QPlainTextEdit.Shape.NoFrame)
        self.setStyleSheet("QPlainTextEdit {background: transparent; border: none; padding: 0px;}")
        self.setAutoFillBackground(False)
        self.viewport().setAutoFillBackground(False)
        self.setCursorWidth(0)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setAcceptDrops(False)
        self.setUndoRedoEnabled(True)
        self.setInputMethodHints(Qt.InputMethodHint.ImhNoPredictiveText)
        self.cursorPositionChanged.connect(self.viewport().update)
        self.textChanged.connect(self.viewport().update)

    def visible_context(self):
        if not self.revealed:
            return ""
        cursor = self.textCursor()
        prefix = cursor.block().text().encode("utf-16-le")[:cursor.positionInBlock() * 2].decode("utf-16-le")
        return tail_characters(prefix, self.context_chars)

    def set_revealed(self, value):
        self.revealed = value
        self.mode_changed.emit(value)
        self.viewport().update()

    def move_cursor(self, direction):
        if self.composing:
            return
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter if direction < 0 else QTextCursor.MoveOperation.NextCharacter)
        self.setTextCursor(cursor)
        self.set_revealed(direction < 0)

    def caret_rect(self):
        x = 4 + self.fontMetrics().horizontalAdvance(self.visible_context())
        return QRectF(x, max(0, (self.viewport().height() - self.fontMetrics().height()) / 2), 1, self.fontMetrics().height())

    def inputMethodQuery(self, query):
        if query in (Qt.InputMethodQuery.ImCursorRectangle, Qt.InputMethodQuery.ImAnchorRectangle):
            return self.caret_rect()
        return super().inputMethodQuery(query)

    def paintEvent(self, event):
        # One transparent line. Never call the document's paint routine: it
        # would expose surrounding history or an opaque selection background.
        painter = QPainter(self.viewport())
        if not self.revealed:
            return
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setPen(QColor("#bcd9ca"))
        rect = self.caret_rect()
        baseline = rect.top() + self.fontMetrics().ascent()
        painter.drawText(4, int(baseline), self.visible_context())
        painter.setPen(QPen(QColor("#dbf0e1"), 1))
        painter.drawLine(int(rect.x()), int(rect.top()), int(rect.x()), int(rect.bottom()))
        if self.preedit:
            painter.drawText(int(rect.x()) + 3, int(baseline), tail_characters(self.preedit, self.context_chars))

    def inputMethodEvent(self, event):
        self.in_ime_event = True
        self.preedit = event.preeditString()
        self.composing = bool(self.preedit)
        self.composition_changed.emit(self.composing)
        try:
            super().inputMethodEvent(event)
        finally:
            self.in_ime_event = False
        if event.commitString() or event.replacementLength() or not self.composing:
            self.ime_committed.emit()
        self.viewport().update()

    def keyPressEvent(self, event):
        if self.composing:
            super().keyPressEvent(event)
            return
        sequence = QKeySequence(event.keyCombination()).toString(QKeySequence.SequenceFormat.PortableText)
        if sequence == "Enter":
            sequence = "Return"
        if self.dispatch(sequence):
            event.accept()
            return
        if sequence in ("Ctrl+C", "Ctrl+X"):
            event.accept()
            return
        if event.key() == Qt.Key.Key_Left:
            self.set_revealed(True)
        elif event.key() == Qt.Key.Key_Right:
            self.set_revealed(False)
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        # Pixel positions are a short context preview, not the full document.
        # Keep the actual insertion point; use arrows to move it precisely.
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        event.accept()

    def mouseMoveEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.accept()

    def replace_document(self, text, position=None):
        previous = self.blockSignals(True)
        self.setPlainText(text)
        cursor = self.textCursor()
        if position is None:
            cursor.movePosition(QTextCursor.MoveOperation.End)
        else:
            cursor.setPosition(min(position, self.document().characterCount() - 1))
        self.setTextCursor(cursor)
        self.blockSignals(previous)
        self.viewport().update()
