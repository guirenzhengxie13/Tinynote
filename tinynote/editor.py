from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QInputMethodEvent, QKeySequence, QPainter, QPen, QTextCursor, QTextLayout, QTextOption
from PySide6.QtWidgets import QPlainTextEdit


def utf16_length(text):
    return len(text.encode("utf-16-le")) // 2


@dataclass
class LineView:
    # Keep the layout alive as long as its QTextLine is used.
    layout: QTextLayout
    text: str
    origin: QPointF
    clip: QRectF
    caret: QRectF

    @property
    def line(self):
        return self.layout.lineAt(0)


class HiddenEditor(QPlainTextEdit):
    ime_committed = Signal()
    composition_changed = Signal(bool)
    mode_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.revealed = False
        self.preedit = ""
        self.preedit_cursor = 0
        self.composing = False
        self.in_ime_event = False
        self.dispatch = lambda sequence: False
        self.conceal_shortcut = "Ctrl+H"
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

    def line_view(self):
        """Lay out one logical line, scrolling around the actual insertion point."""
        cursor = self.textCursor()
        raw = cursor.block().text().encode("utf-16-le")
        position = cursor.positionInBlock()
        text = (raw[:position * 2] + self.preedit.encode("utf-16-le") + raw[position * 2:]).decode("utf-16-le")
        layout = QTextLayout(text, self.font())
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.NoWrap)
        option.setFlags(QTextOption.Flag.IncludeTrailingSpaces)
        layout.setTextOption(option)
        if self.preedit:
            preedit_format = QTextLayout.FormatRange()
            preedit_format.start = position
            preedit_format.length = utf16_length(self.preedit)
            preedit_format.format.setFontUnderline(True)
            layout.setFormats([preedit_format])
        layout.beginLayout()
        line = layout.createLine()
        line.setLineWidth(1_000_000_000)
        layout.endLayout()
        caret_x = line.cursorToX(position + self.preedit_cursor)[0]
        width = max(1, self.viewport().width() - 8)
        # Center a long line around the caret, clamp at either end. Short lines
        # remain left-aligned. Never replace the document with the visible slice.
        scroll = min(max(0, caret_x - width / 2), max(0, line.horizontalAdvance() - width + 1))
        y = max(0, (self.viewport().height() - line.height()) / 2)
        origin = QPointF(4 - scroll, y)
        clip = QRectF(4, 0, width, self.viewport().height())
        caret = QRectF(origin.x() + caret_x, y, 1, line.height())
        return LineView(layout, text, origin, clip, caret)

    def visible_context(self):
        if not self.revealed:
            return ""
        view = self.line_view()
        start = view.line.xToCursor(view.clip.left() - view.origin.x())
        end = view.line.xToCursor(view.clip.right() - view.origin.x())
        return view.text.encode("utf-16-le")[min(start, end) * 2:max(start, end) * 2].decode("utf-16-le")

    def set_revealed(self, value):
        self.revealed = value
        self.mode_changed.emit(value)
        self.viewport().update()

    def move_cursor(self, direction):
        if self.composing:
            return
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor.setPosition(cursor.selectionStart() if direction < 0 else cursor.selectionEnd())
        else:
            cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter if direction < 0 else QTextCursor.MoveOperation.NextCharacter)
        self.setTextCursor(cursor)
        self.set_revealed(True)

    def caret_rect(self):
        if self.revealed:
            return self.line_view().caret
        return QRectF(4, max(0, (self.viewport().height() - self.fontMetrics().height()) / 2), 1, self.fontMetrics().height())

    def inputMethodQuery(self, query):
        if query in (Qt.InputMethodQuery.ImCursorRectangle, Qt.InputMethodQuery.ImAnchorRectangle):
            return self.caret_rect()
        return super().inputMethodQuery(query)

    def paintEvent(self, event):
        # Draw only the current line, clipped to the transparent input area.
        painter = QPainter(self.viewport())
        if not self.revealed:
            return
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setPen(QColor("#bcd9ca"))
        view = self.line_view()
        painter.setClipRect(view.clip)
        selections = []
        cursor = self.textCursor()
        if cursor.hasSelection() and not self.composing:
            start = max(0, cursor.selectionStart() - cursor.block().position())
            end = min(utf16_length(view.text), cursor.selectionEnd() - cursor.block().position())
            if end > start:
                selection = QTextLayout.FormatRange()
                selection.start, selection.length = start, end - start
                selection.format.setBackground(QColor(160, 212, 185, 85))
                selection.format.setForeground(QColor("#effff4"))
                selections.append(selection)
        view.layout.draw(painter, view.origin, selections)
        painter.setPen(QPen(QColor("#dbf0e1"), 1))
        rect = view.caret
        painter.drawLine(int(rect.x()), int(rect.top()), int(rect.x()), int(rect.bottom()))

    def inputMethodEvent(self, event):
        self.in_ime_event = True
        self.preedit = event.preeditString()
        self.preedit_cursor = utf16_length(self.preedit)
        for attribute in event.attributes():
            if attribute.type == QInputMethodEvent.AttributeType.Cursor:
                self.preedit_cursor = max(0, min(attribute.start, utf16_length(self.preedit)))
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
        sequence = QKeySequence(event.keyCombination()).toString(QKeySequence.SequenceFormat.PortableText)
        if sequence == "Enter":
            sequence = "Return"
        # Conceal is a display-only action and remains available while an IME
        # is composing. Other editing/navigation keys still belong to the IME.
        if sequence == self.conceal_shortcut and self.dispatch(sequence):
            event.accept()
            return
        if self.composing:
            super().keyPressEvent(event)
            return
        if self.dispatch(sequence):
            event.accept()
            return
        if sequence in ("Ctrl+C", "Ctrl+X"):
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.set_revealed(True)
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        self.set_revealed(False)
        super().focusOutEvent(event)

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
