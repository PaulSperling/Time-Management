import sys
import json
from datetime import date, datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QTableView, QTableWidget, QTableWidgetItem, QSplitter,
    QPushButton, QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox,
    QDateEdit, QCheckBox, QLabel, QComboBox, QDialog, QDialogButtonBox,
    QMessageBox, QFileDialog, QHeaderView, QProgressBar,
    QListWidget, QListWidgetItem, QAction, QAbstractItemView,
    QCalendarWidget, QFrame, QSizePolicy,
)
from PyQt5.QtCore import (
    Qt, QDate, QTimer, QAbstractTableModel, QModelIndex,
    QSortFilterProxyModel, pyqtSignal,
)
from PyQt5.QtGui import QColor, QFont, QPalette


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class Task:
    def __init__(self, name, description, due_date, do_date, priority,
                 time_estimate, done=False):
        self.name = name
        self.description = description
        self.due_date = due_date
        self.do_date = do_date
        self.priority = priority
        self.time_estimate = time_estimate
        self.done = done

    @property
    def do_today(self):
        return self.do_date == date.today()

    @property
    def urgency_score(self):
        if self.done:
            return 0
        days = (self.due_date - date.today()).days
        if days <= 0:    factor = 10
        elif days <= 3:  factor = 8
        elif days <= 7:  factor = 6
        elif days <= 14: factor = 4
        elif days <= 30: factor = 2
        else:            factor = 1
        return self.priority * factor

    def to_dict(self):
        return {
            'name': self.name,
            'description': self.description,
            'due_date': self.due_date.isoformat(),
            'do_date': self.do_date.isoformat(),
            'priority': self.priority,
            'time_estimate': self.time_estimate,
            'done': self.done,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            name=d['name'],
            description=d['description'],
            due_date=date.fromisoformat(d['due_date']),
            do_date=date.fromisoformat(d['do_date']),
            priority=d['priority'],
            time_estimate=d['time_estimate'],
            done=d.get('done', False),
        )


# ---------------------------------------------------------------------------
# Dark palette — all cell/text colours live here
# ---------------------------------------------------------------------------

CELL_NEUTRAL = QColor(36,  36,  52)
CELL_DONE    = QColor(40,  40,  55)
TEXT_PRIMARY = QColor(205, 214, 244)
TEXT_MUTED   = QColor( 88,  91, 112)
DO_TODAY_BG  = QColor( 36,  92, 170)


def urgency_color(task):
    if task.done:
        return CELL_DONE
    s = task.urgency_score
    if s >= 40: return QColor(108, 24, 30)
    if s >= 25: return QColor(108, 56, 14)
    if s >= 15: return QColor( 92, 76, 10)
    if s >= 5:  return QColor( 22, 76, 34)
    return QColor(26, 48, 92)


def due_date_color(d):
    days = (d - date.today()).days
    if days <  0:  return QColor(118, 20, 26)
    if days == 0:  return QColor(118, 56, 10)
    if days <= 3:  return QColor( 98, 76, 10)
    if days <= 7:  return QColor( 76, 76, 16)
    if days <= 14: return QColor( 26, 70, 34)
    if days <= 30: return QColor( 22, 56, 30)
    return CELL_NEUTRAL


def do_date_color(d):
    days = (d - date.today()).days
    if days <  0:  return QColor( 98, 26, 32)
    if days == 0:  return QColor( 18, 66, 128)
    if days <= 3:  return QColor( 18, 50,  98)
    return CELL_NEUTRAL


_PRIORITY_FG = {
    5: QColor(243, 139, 168),
    4: QColor(250, 179, 135),
    3: QColor(249, 226, 175),
    2: QColor(166, 227, 161),
    1: QColor(137, 180, 250),
}


def priority_color(p):
    return _PRIORITY_FG.get(p, QColor(166, 173, 200))


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def section_label(text):
    """Uppercase accent-coloured section header."""
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        "color: #89b4fa; font-size: 10px; font-weight: bold; "
        "letter-spacing: 2px; padding: 10px 6px 4px 6px;"
    )
    return lbl


def h_rule():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet("background: #313244; border: none;")
    return line


# ---------------------------------------------------------------------------
# Task dialog
# ---------------------------------------------------------------------------

class TaskDialog(QDialog):
    def __init__(self, parent=None, task=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Task" if task else "New Task")
        self.setMinimumWidth(430)
        self._build()
        if task:
            self._populate(task)

    def _build(self):
        layout = QFormLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setLabelAlignment(Qt.AlignRight)

        self.name_edit = QLineEdit()
        self.desc_edit = QTextEdit()
        self.desc_edit.setFixedHeight(72)

        self.due_edit = QDateEdit(calendarPopup=True)
        self.due_edit.setDate(QDate.currentDate().addDays(7))
        self.due_edit.setDisplayFormat("yyyy-MM-dd")

        self.do_edit = QDateEdit(calendarPopup=True)
        self.do_edit.setDate(QDate.currentDate())
        self.do_edit.setDisplayFormat("yyyy-MM-dd")

        self.priority_spin = QSpinBox()
        self.priority_spin.setRange(1, 5)
        self.priority_spin.setValue(3)

        self.time_spin = QDoubleSpinBox()
        self.time_spin.setRange(0.25, 999)
        self.time_spin.setSingleStep(0.25)
        self.time_spin.setValue(1.0)
        self.time_spin.setSuffix(" hrs")

        self.done_check = QCheckBox()

        layout.addRow("Name *", self.name_edit)
        layout.addRow("Description", self.desc_edit)
        layout.addRow("Due Date", self.due_edit)
        layout.addRow("Do Date", self.do_edit)
        layout.addRow("Priority (1–5)", self.priority_spin)
        layout.addRow("Time Estimate", self.time_spin)
        layout.addRow("Done", self.done_check)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def _populate(self, t):
        self.name_edit.setText(t.name)
        self.desc_edit.setPlainText(t.description)
        self.due_edit.setDate(QDate(t.due_date.year, t.due_date.month, t.due_date.day))
        self.do_edit.setDate(QDate(t.do_date.year, t.do_date.month, t.do_date.day))
        self.priority_spin.setValue(t.priority)
        self.time_spin.setValue(t.time_estimate)
        self.done_check.setChecked(t.done)

    def _ok(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Required", "Task name cannot be empty.")
            return
        self.accept()

    def get_task(self):
        d, o = self.due_edit.date(), self.do_edit.date()
        return Task(
            name=self.name_edit.text().strip(),
            description=self.desc_edit.toPlainText().strip(),
            due_date=date(d.year(), d.month(), d.day()),
            do_date=date(o.year(), o.month(), o.day()),
            priority=self.priority_spin.value(),
            time_estimate=self.time_spin.value(),
            done=self.done_check.isChecked(),
        )


# ---------------------------------------------------------------------------
# Task table model
# ---------------------------------------------------------------------------

COLUMNS = ['Name', 'Due Date', 'Do Date', 'Priority', 'Est. Time',
           'Urgency', 'Do Today', 'Done']
COL = {n: i for i, n in enumerate(COLUMNS)}


class TaskTableModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self.tasks = []

    def rowCount(self, parent=QModelIndex()): return len(self.tasks)
    def columnCount(self, parent=QModelIndex()): return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMNS[section]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        t = self.tasks[index.row()]
        c = index.column()

        if role == Qt.DisplayRole:
            if c == COL['Name']:      return t.name
            if c == COL['Due Date']:  return t.due_date.strftime('%Y-%m-%d')
            if c == COL['Do Date']:   return t.do_date.strftime('%Y-%m-%d')
            if c == COL['Priority']:  return str(t.priority)
            if c == COL['Est. Time']: return f"{t.time_estimate:.2f}h"
            if c == COL['Urgency']:   return str(t.urgency_score)
            if c == COL['Do Today']:  return "Yes" if t.do_today else "No"
            if c == COL['Done']:      return "Yes" if t.done else "No"

        if role == Qt.UserRole:
            if c == COL['Name']:      return t.name.lower()
            if c == COL['Due Date']:  return t.due_date.isoformat()
            if c == COL['Do Date']:   return t.do_date.isoformat()
            if c == COL['Priority']:  return t.priority
            if c == COL['Est. Time']: return t.time_estimate
            if c == COL['Urgency']:   return t.urgency_score
            if c == COL['Do Today']:  return int(t.do_today)
            if c == COL['Done']:      return int(t.done)

        if role == Qt.BackgroundRole:
            if t.done:
                return CELL_DONE
            if c == COL['Name']:
                return urgency_color(t)
            if c == COL['Due Date']:
                return due_date_color(t.due_date)
            if c == COL['Do Date']:
                return do_date_color(t.do_date)
            if c == COL['Do Today']:
                return DO_TODAY_BG if t.do_today else CELL_NEUTRAL
            return CELL_NEUTRAL

        if role == Qt.ForegroundRole:
            if t.done:
                return TEXT_MUTED
            if c == COL['Do Today'] and t.do_today:
                return QColor(255, 255, 255)
            if c == COL['Priority']:
                return priority_color(t.priority)
            return TEXT_PRIMARY

        if role == Qt.FontRole:
            f = QFont()
            if t.do_today and not t.done: f.setBold(True)
            if t.done: f.setStrikeOut(True)
            return f

        if role == Qt.TextAlignmentRole:
            if c == COL['Name']: return int(Qt.AlignLeft | Qt.AlignVCenter)
            return int(Qt.AlignCenter)

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable


# ---------------------------------------------------------------------------
# Task page  (right panel)
# ---------------------------------------------------------------------------

class TaskPage(QWidget):
    tasks_changed = pyqtSignal()

    def __init__(self, tasks):
        super().__init__()
        self.tasks = tasks
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(section_label("Tasks"))
        layout.addWidget(h_rule())

        inner = QVBoxLayout()
        inner.setContentsMargins(10, 8, 10, 10)
        inner.setSpacing(8)

        # toolbar
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self._add_btn  = QPushButton("+ Add")
        self._edit_btn = QPushButton("Edit")
        self._del_btn  = QPushButton("Delete")
        self._done_btn = QPushButton("Toggle Done")
        for btn in (self._add_btn, self._edit_btn, self._del_btn, self._done_btn):
            bar.addWidget(btn)
        bar.addStretch()

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All Tasks", "Incomplete", "Do Today", "Overdue", "Done"])
        self.filter_combo.currentIndexChanged.connect(self._refresh)
        self.filter_combo.setMaximumWidth(120)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search…")
        self.search_edit.textChanged.connect(self._refresh)
        self.search_edit.setMaximumWidth(170)

        bar.addWidget(QLabel("Filter:"))
        bar.addWidget(self.filter_combo)
        bar.addWidget(QLabel("Search:"))
        bar.addWidget(self.search_edit)
        inner.addLayout(bar)

        # table
        self.model = TaskTableModel()
        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(Qt.UserRole)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(COL['Name'], QHeaderView.Stretch)
        for c in range(1, len(COLUMNS)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.doubleClicked.connect(self._edit_task)
        self.table.selectionModel().currentRowChanged.connect(self._on_select)
        self.proxy.sort(COL['Urgency'], Qt.DescendingOrder)
        inner.addWidget(self.table)

        # description strip
        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet(
            "background: #252538; color: #a6adc8; font-size: 11px; "
            "padding: 8px 10px; border: 1px solid #313244; border-radius: 5px;"
        )
        self.desc_label.setFixedHeight(46)
        self.desc_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        inner.addWidget(self.desc_label)

        # legend
        leg = QHBoxLayout()
        leg.setSpacing(8)
        leg.addWidget(QLabel("Name colour:"))
        for color, lbl_text in [
            (QColor(108, 24, 30),  "Critical"),
            (QColor(108, 56, 14),  "High"),
            (QColor( 92, 76, 10),  "Medium"),
            (QColor( 22, 76, 34),  "Low"),
            (QColor( 26, 48, 92),  "Minimal"),
            (CELL_DONE,            "Done"),
        ]:
            swatch = QLabel()
            swatch.setFixedSize(12, 12)
            swatch.setStyleSheet(
                f"background: rgb({color.red()},{color.green()},{color.blue()}); "
                "border-radius: 3px;"
            )
            lbl = QLabel(lbl_text)
            lbl.setStyleSheet("color: #585b70; font-size: 10px;")
            leg.addWidget(swatch)
            leg.addWidget(lbl)
        leg.addStretch()
        inner.addLayout(leg)

        layout.addLayout(inner)

        self._add_btn.clicked.connect(self._add_task)
        self._edit_btn.clicked.connect(self._edit_task)
        self._del_btn.clicked.connect(self._delete_task)
        self._done_btn.clicked.connect(self._toggle_done)

        self._refresh()

    def _filtered_tasks(self):
        f = self.filter_combo.currentText()
        q = self.search_edit.text().strip().lower()
        today = date.today()
        out = []
        for t in self.tasks:
            if f == "Incomplete" and t.done: continue
            if f == "Do Today" and not t.do_today: continue
            if f == "Overdue" and (t.done or t.due_date >= today): continue
            if f == "Done" and not t.done: continue
            if q and q not in t.name.lower() and q not in t.description.lower(): continue
            out.append(t)
        return out

    def _refresh(self):
        self.model.beginResetModel()
        self.model.tasks = self._filtered_tasks()
        self.model.endResetModel()
        self.desc_label.clear()

    def refresh(self): self._refresh()

    def _on_select(self, current, _prev):
        src = self.proxy.mapToSource(current)
        if src.isValid() and 0 <= src.row() < len(self.model.tasks):
            t = self.model.tasks[src.row()]
            self.desc_label.setText(t.description or "<i>no description</i>")

    def _selected(self):
        src = self.proxy.mapToSource(self.table.currentIndex())
        if not src.isValid() or src.row() >= len(self.model.tasks):
            return None, None
        task = self.model.tasks[src.row()]
        try:
            return self.tasks.index(task), task
        except ValueError:
            return None, None

    def _add_task(self):
        dlg = TaskDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self.tasks.append(dlg.get_task())
            self._refresh(); self.tasks_changed.emit()

    def _edit_task(self):
        i, task = self._selected()
        if task is None: return
        dlg = TaskDialog(self, task)
        if dlg.exec_() == QDialog.Accepted:
            self.tasks[i] = dlg.get_task()
            self._refresh(); self.tasks_changed.emit()

    def _delete_task(self):
        i, task = self._selected()
        if task is None: return
        if QMessageBox.question(self, "Delete", f"Delete '{task.name}'?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.tasks.pop(i)
            self._refresh(); self.tasks_changed.emit()

    def _toggle_done(self):
        i, task = self._selected()
        if task is None: return
        self.tasks[i].done = not self.tasks[i].done
        self._refresh(); self.tasks_changed.emit()


# ---------------------------------------------------------------------------
# Overview page  (top-left)
# ---------------------------------------------------------------------------

class OverviewPage(QWidget):
    def __init__(self, tasks):
        super().__init__()
        self.tasks = tasks
        self._build()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_time)
        self._timer.start(30_000)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(section_label("Overview"))
        layout.addWidget(h_rule())

        inner = QVBoxLayout()
        inner.setContentsMargins(10, 8, 10, 8)
        inner.setSpacing(8)

        # stat cards row
        cards_row = QHBoxLayout()
        cards_row.setSpacing(8)

        for attr, title in [('_lbl_left', 'TIME LEFT'), ('_lbl_alloc', 'ALLOCATED'), ('_lbl_pct', 'USAGE')]:
            card = QFrame()
            card.setStyleSheet(
                "QFrame { background: #252538; border: 1px solid #2e2e48; border-radius: 7px; }"
            )
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 8, 12, 8)
            cl.setSpacing(2)
            t_lbl = QLabel(title)
            t_lbl.setStyleSheet("color: #585b70; font-size: 9px; font-weight: bold; letter-spacing: 1px; background: transparent; border: none;")
            v_lbl = QLabel("—")
            v_lbl.setStyleSheet("color: #cdd6f4; font-size: 18px; font-weight: bold; background: transparent; border: none;")
            cl.addWidget(t_lbl)
            cl.addWidget(v_lbl)
            setattr(self, attr, v_lbl)
            cards_row.addWidget(card)

        inner.addLayout(cards_row)

        # progress bar
        self.bar = QProgressBar()
        self.bar.setMaximum(200)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        inner.addWidget(self.bar)

        # top-10 table
        top_lbl = QLabel("TOP 10 MOST URGENT")
        top_lbl.setStyleSheet("color: #585b70; font-size: 9px; font-weight: bold; letter-spacing: 1px; padding-top: 4px;")
        inner.addWidget(top_lbl)

        self.urgent_table = QTableWidget(0, 6)
        self.urgent_table.setHorizontalHeaderLabels(['Name', 'Due', 'Pri', 'Urg', 'Time', 'Today'])
        hh = self.urgent_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 6):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.urgent_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.urgent_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.urgent_table.verticalHeader().setVisible(False)
        inner.addWidget(self.urgent_table)

        layout.addLayout(inner)
        self.refresh()

    def refresh(self):
        self._update_time()
        self._update_urgent()

    def _update_time(self):
        now = datetime.now()
        eod = now.replace(hour=17, minute=0, second=0, microsecond=0)
        if now >= eod:
            left_h = 0.0
            self._lbl_left.setText("0h 0m")
        else:
            delta = eod - now
            mins = delta.seconds // 60
            h, m = divmod(mins, 60)
            left_h = mins / 60.0
            self._lbl_left.setText(f"{h}h {m}m")

        allocated = sum(t.time_estimate for t in self.tasks if t.do_today and not t.done)
        self._lbl_alloc.setText(f"{allocated:.1f}h")

        pct = round((allocated / left_h * 100) if left_h > 0 else (200 if allocated > 0 else 0))
        self.bar.setValue(min(200, pct))

        if pct > 150:
            bar_hex, text_color = "#c0201e", "#f38ba8"
        elif pct >= 100:
            bar_hex, text_color = "#b89800", "#f9e2af"
        else:
            bar_hex, text_color = "#1a6fbe", "#89b4fa"

        self._lbl_pct.setText(f"{pct}%")
        self._lbl_pct.setStyleSheet(
            f"color: {text_color}; font-size: 18px; font-weight: bold; background: transparent; border: none;"
        )
        self.bar.setStyleSheet(
            "QProgressBar { background: #252538; border: none; border-radius: 4px; }"
            f"QProgressBar::chunk {{ background: {bar_hex}; border-radius: 4px; }}"
        )

    def _update_urgent(self):
        top10 = sorted(
            (t for t in self.tasks if not t.done),
            key=lambda t: t.urgency_score, reverse=True
        )[:10]

        self.urgent_table.setRowCount(len(top10))
        for row, t in enumerate(top10):
            bg = urgency_color(t)
            cells = [
                (t.name,                         Qt.AlignLeft | Qt.AlignVCenter),
                (t.due_date.strftime('%m/%d/%y'), Qt.AlignCenter),
                (str(t.priority),                Qt.AlignCenter),
                (str(t.urgency_score),           Qt.AlignCenter),
                (f"{t.time_estimate:.1f}h",      Qt.AlignCenter),
                ("Yes" if t.do_today else "No",  Qt.AlignCenter),
            ]
            for col, (text, align) in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(int(align))
                item.setBackground(bg)
                item.setForeground(TEXT_PRIMARY)
                if col == 2:
                    item.setForeground(priority_color(t.priority))
                    f = item.font(); f.setBold(True); item.setFont(f)
                if col == 5 and t.do_today:
                    item.setBackground(DO_TODAY_BG)
                self.urgent_table.setItem(row, col, item)


# ---------------------------------------------------------------------------
# Calendar page  (bottom-left)
# ---------------------------------------------------------------------------

class TaskCalendar(QCalendarWidget):
    def __init__(self, tasks):
        super().__init__()
        self.tasks = tasks
        self.setGridVisible(True)
        self.setMinimumDate(QDate(2000, 1, 1))
        self.setMaximumDate(QDate(2099, 12, 31))

    def paintCell(self, painter, rect, qdate):
        super().paintCell(painter, rect, qdate)
        py = date(qdate.year(), qdate.month(), qdate.day())
        do_t  = [t for t in self.tasks if not t.done and t.do_date  == py]
        due_t = [t for t in self.tasks if not t.done and t.due_date == py]
        if not do_t and not due_t:
            return
        painter.save()
        r = 4
        x = rect.left() + 3
        y = rect.bottom() - r * 2 - 2
        if do_t:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(80, 148, 236, 220))
            painter.drawEllipse(x, y, r * 2, r * 2)
            x += r * 2 + 3
        if due_t:
            painter.setPen(Qt.NoPen)
            ms = max(t.urgency_score for t in due_t)
            if ms >= 40:   c = QColor(228, 58, 58, 220)
            elif ms >= 25: c = QColor(218, 128, 38, 220)
            else:          c = QColor(196, 172, 38, 220)
            painter.setBrush(c)
            painter.drawEllipse(x, y, r * 2, r * 2)
        painter.restore()


class CalendarPage(QWidget):
    def __init__(self, tasks):
        super().__init__()
        self.tasks = tasks
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(section_label("Calendar"))
        layout.addWidget(h_rule())

        inner = QVBoxLayout()
        inner.setContentsMargins(10, 6, 10, 8)
        inner.setSpacing(6)

        self.cal = TaskCalendar(self.tasks)
        self.cal.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.cal.clicked.connect(self._on_click)
        inner.addWidget(self.cal)

        # legend
        leg = QHBoxLayout()
        leg.setSpacing(6)
        for rgb, lbl_text in [
            ((80, 148, 236), "Do date"),
            ((228,  58,  58), "Due (crit)"),
            ((218, 128,  38), "Due (high)"),
            ((196, 172,  38), "Due (low)"),
        ]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: rgb{rgb}; font-size: 13px; background: transparent;")
            lbl = QLabel(lbl_text)
            lbl.setStyleSheet("color: #585b70; font-size: 10px;")
            leg.addWidget(dot)
            leg.addWidget(lbl)
        leg.addStretch()
        inner.addLayout(leg)

        self.date_lbl = QLabel("Select a date")
        self.date_lbl.setStyleSheet(
            "color: #89b4fa; font-size: 11px; font-weight: bold; padding: 2px 0;"
        )
        inner.addWidget(self.date_lbl)

        self.task_list = QListWidget()
        self.task_list.setMaximumHeight(110)
        self.task_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        inner.addWidget(self.task_list)

        layout.addLayout(inner)

    def _on_click(self, qdate):
        py = date(qdate.year(), qdate.month(), qdate.day())
        self.date_lbl.setText(py.strftime('%A, %B %d, %Y'))
        self.task_list.clear()
        for t in self.tasks:
            if t.due_date != py and t.do_date != py:
                continue
            tags = []
            if t.do_date  == py: tags.append("DO")
            if t.due_date == py: tags.append("DUE")
            if t.done:           tags.append("DONE")
            item = QListWidgetItem(f"[{'/'.join(tags)}]  {t.name}")
            item.setBackground(urgency_color(t))
            item.setForeground(TEXT_MUTED if t.done else TEXT_PRIMARY)
            if t.done:
                f = item.font(); f.setStrikeOut(True); item.setFont(f)
            self.task_list.addItem(item)

    def refresh(self):
        self.cal.update()


# ---------------------------------------------------------------------------
# Dark stylesheet
# ---------------------------------------------------------------------------

DARK_STYLE = """
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Segoe UI', 'Arial', sans-serif;
    font-size: 12px;
    border: none;
}
QMainWindow, QDialog { background-color: #181825; }

/* ── Menu bar ── */
QMenuBar {
    background-color: #181825;
    border-bottom: 1px solid #2a2a3e;
    padding: 2px 6px;
    spacing: 2px;
}
QMenuBar::item { padding: 4px 12px; border-radius: 4px; color: #a6adc8; }
QMenuBar::item:selected { background: #313244; color: #cdd6f4; }

QMenu {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 8px;
    padding: 6px 0;
}
QMenu::item { padding: 6px 28px 6px 14px; border-radius: 4px; margin: 1px 4px; }
QMenu::item:selected { background: #45475a; }
QMenu::separator { height: 1px; background: #45475a; margin: 4px 10px; }

/* ── Splitter ── */
QSplitter::handle { background: #252538; }
QSplitter::handle:horizontal { width: 3px; }
QSplitter::handle:vertical   { height: 3px; }
QSplitter::handle:hover { background: #89b4fa; }

/* ── Buttons ── */
QPushButton {
    background-color: #2a2a42;
    color: #cdd6f4;
    border: 1px solid #3a3a58;
    border-radius: 6px;
    padding: 5px 14px;
    font-weight: 500;
}
QPushButton:hover   { background: #3a3a56; border-color: #89b4fa; color: #ffffff; }
QPushButton:pressed { background: #4a4a66; }

/* ── Text inputs ── */
QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit {
    background-color: #252538;
    color: #cdd6f4;
    border: 1px solid #3a3a58;
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: #4a6ea8;
    selection-color: #ffffff;
}
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QDateEdit:focus { border-color: #89b4fa; }

QSpinBox::up-button, QDoubleSpinBox::up-button, QDateEdit::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button, QDateEdit::down-button {
    background: #3a3a58; border: none; width: 16px; border-radius: 3px;
}
QDateEdit::drop-down { background: #3a3a58; border: none; width: 20px; border-radius: 3px; }

/* ── Combo box ── */
QComboBox {
    background-color: #252538;
    color: #cdd6f4;
    border: 1px solid #3a3a58;
    border-radius: 6px;
    padding: 4px 8px;
}
QComboBox:hover { border-color: #89b4fa; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    selection-background-color: #45475a;
    outline: none;
}

/* ── Tables ── */
QTableView, QTableWidget {
    background-color: #1e1e2e;
    gridline-color: #28283e;
    border: 1px solid #2a2a42;
    border-radius: 6px;
    outline: none;
}
QTableView::item, QTableWidget::item { padding: 3px 6px; }
QTableView::item:selected, QTableWidget::item:selected {
    background-color: rgba(69, 71, 112, 180);
    color: #ffffff;
}
QHeaderView { background: transparent; border: none; }
QHeaderView::section {
    background-color: #181825;
    color: #45475a;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 1px;
    padding: 6px 8px;
    border: none;
    border-right: 1px solid #2a2a3e;
    border-bottom: 1px solid #2a2a3e;
    text-transform: uppercase;
}
QHeaderView::section:first { border-top-left-radius: 5px; }
QHeaderView::section:last  { border-right: none; }

/* ── Scroll bars ── */
QScrollBar:vertical {
    background: #1e1e2e; width: 6px; border-radius: 3px; margin: 0;
}
QScrollBar::handle:vertical {
    background: #3a3a58; border-radius: 3px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #4a4a6e; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #1e1e2e; height: 6px; border-radius: 3px; margin: 0;
}
QScrollBar::handle:horizontal {
    background: #3a3a58; border-radius: 3px; min-width: 24px;
}
QScrollBar::handle:horizontal:hover { background: #4a4a6e; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── List widget ── */
QListWidget {
    background-color: #1e1e2e;
    border: 1px solid #2a2a42;
    border-radius: 6px;
    outline: none;
}
QListWidget::item { padding: 4px 8px; border-radius: 3px; margin: 1px 2px; }
QListWidget::item:selected { background-color: #3a3a58; color: #ffffff; }

/* ── Calendar ── */
QCalendarWidget QToolButton {
    background: transparent;
    color: #cdd6f4;
    border: none;
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 12px;
    font-weight: bold;
}
QCalendarWidget QToolButton:hover { background: #2a2a42; }
QCalendarWidget QMenu {
    background: #313244; color: #cdd6f4; border: 1px solid #45475a;
}
QCalendarWidget QSpinBox {
    background: #252538; color: #cdd6f4;
    border: 1px solid #3a3a58; border-radius: 4px; padding: 2px 6px;
}
QCalendarWidget QAbstractItemView:enabled {
    background-color: #1e1e2e;
    color: #cdd6f4;
    selection-background-color: #4a6ea8;
    selection-color: #ffffff;
}
QCalendarWidget QAbstractItemView:disabled { color: #3a3a58; }
QCalendarWidget QWidget#qt_calendar_navigationbar {
    background: #181825;
    border-bottom: 1px solid #2a2a3e;
}

/* ── Progress bar (base — bar colours set dynamically) ── */
QProgressBar { background: #252538; border: none; border-radius: 4px; }
QProgressBar::chunk { border-radius: 4px; }

/* ── Status bar ── */
QStatusBar {
    background: #181825;
    color: #3a3a58;
    border-top: 1px solid #2a2a3e;
    font-size: 10px;
}
QStatusBar::item { border: none; }

/* ── Checkbox ── */
QCheckBox { color: #cdd6f4; spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border-radius: 4px;
    border: 1px solid #3a3a58;
    background: #252538;
}
QCheckBox::indicator:checked { background: #89b4fa; border-color: #89b4fa; }

/* ── Dialog ── */
QDialogButtonBox QPushButton { min-width: 80px; }
QFormLayout QLabel { color: #a6adc8; }

/* ── Tooltip ── */
QToolTip {
    background: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 5px;
    padding: 4px 8px;
}
"""


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.tasks = []
        self.current_file = None
        self._build()
        self._update_title()

    def _build(self):
        self.setMinimumSize(1150, 740)

        # menu
        mb = self.menuBar()
        fm = mb.addMenu("File")
        for label, shortcut, slot in [
            ("New",       "Ctrl+N",       self._new),
            ("Open…",     "Ctrl+O",       self._open),
            (None, None, None),
            ("Save",      "Ctrl+S",       self._save),
            ("Save As…",  "Ctrl+Shift+S", self._save_as),
        ]:
            if label is None:
                fm.addSeparator()
            else:
                a = QAction(label, self)
                a.setShortcut(shortcut)
                a.triggered.connect(slot)
                fm.addAction(a)

        # pages (all share the same task list object)
        self.overview_page = OverviewPage(self.tasks)
        self.task_page     = TaskPage(self.tasks)
        self.calendar_page = CalendarPage(self.tasks)

        # left column: overview on top, calendar below
        left_split = QSplitter(Qt.Vertical)
        left_split.addWidget(self.overview_page)
        left_split.addWidget(self.calendar_page)
        left_split.setSizes([420, 380])
        left_split.setChildrenCollapsible(False)

        # main horizontal split
        main_split = QSplitter(Qt.Horizontal)
        main_split.addWidget(left_split)
        main_split.addWidget(self.task_page)
        main_split.setSizes([420, 730])
        main_split.setChildrenCollapsible(False)

        self.setCentralWidget(main_split)

        self.task_page.tasks_changed.connect(self._propagate)

        self.status_lbl = QLabel()
        self.statusBar().addWidget(self.status_lbl)

    def _propagate(self):
        self.overview_page.refresh()
        self.calendar_page.refresh()

    def _update_title(self):
        name = self.current_file or "Untitled"
        self.setWindowTitle(f"ToDo List — {name}")
        self.status_lbl.setText(name)

    def _refresh_all(self):
        self.task_page.refresh()
        self.overview_page.refresh()
        self.calendar_page.refresh()

    def _new(self):
        self.tasks.clear()
        self.current_file = None
        self._refresh_all()
        self._update_title()

    def _open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Task Database", "", "JSON Files (*.json);;All Files (*)")
        if not path: return
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            self.tasks.clear()
            self.tasks.extend(Task.from_dict(d) for d in data)
            self.current_file = path
            self._refresh_all()
            self._update_title()
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))

    def _save(self):
        if self.current_file: self._write(self.current_file)
        else: self._save_as()

    def _save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Task Database", "", "JSON Files (*.json);;All Files (*)")
        if path:
            self._write(path)
            self.current_file = path
            self._update_title()

    def _write(self, path):
        try:
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump([t.to_dict() for t in self.tasks], fh, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))


# ---------------------------------------------------------------------------

def _dark_palette():
    p = QPalette()
    bg      = QColor(30,  30,  46)
    surface = QColor(37,  37,  56)
    text    = QColor(205, 214, 244)
    subtext = QColor(166, 173, 200)
    accent  = QColor(137, 180, 250)
    p.setColor(QPalette.Window,          bg)
    p.setColor(QPalette.WindowText,      text)
    p.setColor(QPalette.Base,            surface)
    p.setColor(QPalette.AlternateBase,   QColor(42, 42, 62))
    p.setColor(QPalette.Text,            text)
    p.setColor(QPalette.BrightText,      QColor(255, 100, 100))
    p.setColor(QPalette.Button,          surface)
    p.setColor(QPalette.ButtonText,      text)
    p.setColor(QPalette.Highlight,       accent)
    p.setColor(QPalette.HighlightedText, bg)
    p.setColor(QPalette.ToolTipBase,     QColor(49, 50, 68))
    p.setColor(QPalette.ToolTipText,     text)
    p.setColor(QPalette.PlaceholderText, subtext)
    p.setColor(QPalette.Link,            accent)
    return p


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ToDo List")
    app.setPalette(_dark_palette())
    app.setStyleSheet(DARK_STYLE)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
