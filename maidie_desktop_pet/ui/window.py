from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QCursor, QKeyEvent, QMouseEvent, QResizeEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QVBoxLayout, QWidget

from core.chat.bubble_controller import BubbleController
from input.resize import EdgeResizeController
from input.gesture import PetGestureRecognizer
from ui.bubble import SpeechBubble
from ui.chat_input import ChatInput
from ui.dialogs import RecentChatsDialog, SettingsDialog
from ui.resize_handle import SubtleResizeHandle
from ui.sprite import HatchPetSprite


class PetWindow(QWidget):
    """Presentation-only window: renders controller signals and forwards input."""

    def __init__(self, controller, assets_dir: Path, options: dict | None = None,
                 confirmation_broker=None):
        super().__init__()
        options = options or {}
        self.controller = controller
        self.assets_dir = assets_dir
        self._drag_offset: QPoint | None = None
        self._press_local: QPoint | None = None
        self._drag_start_pos: QPoint | None = None
        self._was_dragged = False
        self._pending_click_region: str | None = None
        self._suppress_release_after_double_click = False
        self._single_click_timer = QTimer(self)
        self._single_click_timer.setSingleShot(True)
        self._single_click_timer.timeout.connect(self._perform_single_click)
        self._resize = EdgeResizeController(self)
        self._gesture = PetGestureRecognizer()
        self._gesture_consumed = False
        self._dialog = None
        self.confirmation_broker = confirmation_broker
        if confirmation_broker:
            confirmation_broker.requested.connect(self._confirm_system_action)

        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if options.get("always_on_top", True):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setWindowOpacity(float(options.get("opacity", 1.0)))
        self.setMinimumSize(
            int(options.get("minimum_width", 36)),
            int(options.get("minimum_height", 43)),
        )
        self.resize(int(options.get("width", 320)), int(options.get("height", 380)))

        self.bubble = SpeechBubble(self)
        self.bubble_controller = BubbleController(self.bubble, self._position_overlays, self)
        self.character = HatchPetSprite(assets_dir / "spritesheet.webp")
        self.chat_input = ChatInput(self)
        self.chat_input.submitted.connect(controller.submit_text)
        self.resize_handle = SubtleResizeHandle(self)
        self._handle_visibility_timer = QTimer(self)
        self._handle_visibility_timer.timeout.connect(self._update_resize_handle_visibility)
        self._handle_visibility_timer.start(60)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.addWidget(self.character, stretch=1)

        controller.animation_changed.connect(self.character.set_animation)
        controller.message_received.connect(self._show_reply)
        controller.stream_started.connect(self._start_stream)
        controller.message_delta.connect(self._append_stream)
        controller.position_requested.connect(self._move_from_controller)
        controller.gaze_changed.connect(self.character.set_gaze)
        controller.facing_changed.connect(self.character.set_facing_right)
        self.character.set_facing_right(controller.direction.facing_right)
        self.character.set_animation("idle")
        self._move_to_bottom_right()
        self._position_overlays()
        self.resize_handle.raise_()

    def _confirm_system_action(self, request: dict) -> None:
        action = str(request.get("action", "system action"))
        params = request.get("params", {})
        safe_params = {key: value for key, value in params.items() if key not in {"content", "text"}}
        answer = QMessageBox.question(
            self,
            "Maidie 请求系统权限",
            f"是否允许执行：{action}\n参数：{safe_params}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        self.confirmation_broker.resolve(
            str(request.get("id", "")), answer == QMessageBox.StandardButton.Yes
        )

    def global_rect(self):
        return self.frameGeometry()

    def _move_to_bottom_right(self) -> None:
        screen = self.screen().availableGeometry()
        self.move(screen.right() - self.width() - 24, screen.bottom() - self.height() - 24)
        self._sync_controller_geometry()

    def _sync_controller_geometry(self) -> None:
        geometry = self.frameGeometry()
        self.controller.sync_geometry(
            geometry.x(), geometry.y(), geometry.width(), geometry.height()
        )
        screen = self.screen().availableGeometry()
        self.controller.set_screen_bounds(screen.left(), screen.top(), screen.right() + 1, screen.bottom() + 1)

    def _move_from_controller(self, x: float, y: float) -> None:
        self.move(round(x), round(y))

    def _show_reply(self, response: dict) -> None:
        self.bubble_controller.complete_stream(response)

    def _start_stream(self, metadata: dict) -> None:
        self.bubble_controller.begin_stream(metadata)

    def _append_stream(self, delta: str) -> None:
        self.bubble_controller.append_text(delta)

    def open_chat(self) -> None:
        self.controller.on_chat_opened()
        self._position_overlays()
        self.chat_input.open()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        global_pos = event.globalPosition().toPoint()
        local_pos = event.position().toPoint()
        if event.button() == Qt.MouseButton.LeftButton:
            if self._resize.begin_native(global_pos, local_pos):
                return
            self._press_local = local_pos
            self._drag_start_pos = self.frameGeometry().topLeft()
            character_point = self.character.mapFrom(self, local_pos)
            region = self.character.interaction_region(character_point)
            self._gesture.begin(region, local_pos, self.width())
            self._gesture_consumed = False
            self._drag_offset = global_pos - self.frameGeometry().topLeft()
            self._was_dragged = False
        elif event.button() == Qt.MouseButton.RightButton:
            menu = QMenu(self)
            menu.addAction("和 Maidie 对话", self.open_chat)
            menu.addAction("最近聊天", self.show_recent_chats)
            menu.addAction("性格与模型设置", self.show_settings)
            menu.addSeparator()
            menu.addAction("放大 10%", lambda: self.scale_window(1.1))
            menu.addAction("缩小 10%", lambda: self.scale_window(0.9))
            menu.addAction("恢复默认大小", lambda: self.resize(320, 380))
            menu.addAction("清除记忆", self.controller.clear_memory)
            menu.addSeparator()
            menu.addAction("退出 Maidie", self.close)
            menu.exec(global_pos)

    def show_recent_chats(self) -> None:
        self._dialog = RecentChatsDialog(self.controller, self)
        self._dialog.exec()

    def show_settings(self) -> None:
        self._dialog = SettingsDialog(self.controller, self)
        if self._dialog.exec():
            self.bubble.show_message("设置已经保存好啦。")
            self._position_overlays()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        global_pos = event.globalPosition().toPoint()
        if self._resize.update(global_pos):
            self._was_dragged = True
            return
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            outcome = self._gesture.update(event.position().toPoint())
            if outcome == "headpat":
                self.controller.on_headpat()
                self._gesture_consumed = True
                return
            if outcome == "pending" or self._gesture_consumed:
                return
            self.move(global_pos - self._drag_offset)
            self._was_dragged = True
            return
        edges = self._resize.hit_test(event.position().toPoint())
        diagonal = bool(edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge) and edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge))
        if diagonal:
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.unsetCursor()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        was_resizing = bool(self._resize.edges)
        self._resize.end()
        if self._suppress_release_after_double_click:
            self._suppress_release_after_double_click = False
        elif self._gesture_consumed:
            pass
        elif self._drag_offset is not None and not self._was_dragged and not was_resizing:
            press_point = self._press_local or event.position().toPoint()
            character_point = self.character.mapFrom(self, press_point)
            region = self.character.interaction_region(character_point)
            self._pending_click_region = region
            self._single_click_timer.start(QApplication.doubleClickInterval() + 20)
        elif self._was_dragged:
            geometry = self.frameGeometry()
            drag_dx = (
                geometry.x() - self._drag_start_pos.x() if self._drag_start_pos else 0
            )
            self.controller.on_pet_dragged(
                geometry.x(), geometry.y(), geometry.width(), geometry.height(), drag_dx
            )
        self._drag_offset = None
        self._press_local = None
        self._drag_start_pos = None
        self._gesture.reset()
        self._gesture_consumed = False
        self._was_dragged = False

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._single_click_timer.stop()
            self._pending_click_region = None
            self._suppress_release_after_double_click = True
            self.open_chat()
            event.accept()

    def _perform_single_click(self) -> None:
        region = self._pending_click_region
        self._pending_click_region = None
        if region == "head":
            self.controller.on_headpat()
        elif region == "face":
            self.controller.on_facepoke()
        elif region:
            self.controller.on_pet_clicked()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.open_chat()
            event.accept()
            return
        super().keyPressEvent(event)

    def enterEvent(self, event) -> None:
        self.resize_handle.show()
        self.resize_handle.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        # Do not hide here: transparent parent/child transitions can emit a
        # misleading leave event. The global rectangle poll is authoritative.
        super().leaveEvent(event)

    def _update_resize_handle_visibility(self) -> None:
        inside_window = self.frameGeometry().contains(QCursor.pos())
        should_show = inside_window or self.resize_handle.is_resizing
        if should_show and not self.resize_handle.isVisible():
            self.resize_handle.show()
            self.resize_handle.raise_()
        elif not should_show and self.resize_handle.isVisible():
            self.resize_handle.hide()

    def wheelEvent(self, event: QWheelEvent) -> None:
        self.scale_window(1.08 if event.angleDelta().y() > 0 else 0.92)
        event.accept()

    def scale_window(self, factor: float) -> None:
        """Scale both dimensions together while keeping the pet centered."""
        old = self.geometry()
        factor = max(
            self.minimumWidth() / old.width(),
            self.minimumHeight() / old.height(),
            min(factor, 900 / old.width(), 1069 / old.height()),
        )
        new_width = round(old.width() * factor)
        new_height = round(old.height() * factor)
        center = old.center()
        self.resize(new_width, new_height)
        self.move(center.x() - new_width // 2, center.y() - new_height // 2)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._sync_controller_geometry()
        self._position_overlays()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        width = event.size().width()
        if width < 100:
            self.bubble.hide()
            self.chat_input.hide()
        self.bubble.scale_for_window(width)
        handle_size = 10 if width < 100 else 14 if width < 180 else 18
        self.resize_handle.setFixedSize(handle_size, handle_size)
        self.resize_handle.move(
            event.size().width() - self.resize_handle.width() - 2,
            event.size().height() - self.resize_handle.height() - 2,
        )
        self._position_overlays()
        self.resize_handle.raise_()
        self._sync_controller_geometry()

    def _position_overlays(self) -> None:
        """Position floating UI without changing the character's layout size."""
        if not hasattr(self, "bubble") or not hasattr(self, "chat_input"):
            return
        bubble_width = min(max(120, self.width() - 24), 300)
        self.bubble.setMinimumWidth(min(120, bubble_width))
        self.bubble.setMaximumWidth(bubble_width)
        screen = self.screen().availableGeometry()
        gap = 2
        self.bubble.set_tail("bottom")
        self.bubble.adjustSize()
        above_x = self.x() + (self.width() - self.bubble.width()) // 2
        above_y = self.y() - self.bubble.height() - gap
        if above_y >= screen.top():
            bubble_x, bubble_y = above_x, above_y
        else:
            self.bubble.set_tail("left")
            self.bubble.adjustSize()
        if above_y < screen.top() and self.x() + self.width() + gap + self.bubble.width() <= screen.right():
            bubble_x = self.x() + self.width() + gap
            bubble_y = self.y() + (self.height() - self.bubble.height()) // 2
        elif above_y < screen.top():
            self.bubble.set_tail("right")
            self.bubble.adjustSize()
            if self.x() - gap - self.bubble.width() >= screen.left():
                bubble_x = self.x() - gap - self.bubble.width()
                bubble_y = self.y() + (self.height() - self.bubble.height()) // 2
            else:
                self.bubble.set_tail("top")
                self.bubble.adjustSize()
                bubble_x = self.x() + (self.width() - self.bubble.width()) // 2
                bubble_y = self.y() + self.height() + gap
        bubble_x = max(screen.left(), min(screen.right() - self.bubble.width() + 1, bubble_x))
        bubble_y = max(screen.top(), min(screen.bottom() - self.bubble.height() + 1, bubble_y))
        self.bubble.move(bubble_x, bubble_y)

        input_width = min(360, max(190, self.width()))
        input_height = 40
        pet_rect = self.frameGeometry()
        occupied = [pet_rect]
        if self.bubble.isVisible():
            occupied.append(self.bubble.frameGeometry())
        candidates = [
            QRect(self.x() + (self.width() - input_width) // 2, self.y() + self.height() + 4, input_width, input_height),
            QRect(self.x() + self.width() + 4, self.y() + (self.height() - input_height) // 2, input_width, input_height),
            QRect(self.x() - input_width - 4, self.y() + (self.height() - input_height) // 2, input_width, input_height),
            QRect(self.x() + (self.width() - input_width) // 2, self.y() - input_height - 4, input_width, input_height),
        ]
        chosen = candidates[-1]
        for candidate in candidates:
            if screen.contains(candidate) and not any(candidate.intersects(rect) for rect in occupied):
                chosen = candidate
                break
        self.chat_input.setGeometry(chosen)

    def closeEvent(self, event) -> None:
        self.bubble.close()
        self.chat_input.close()
        self.controller.shutdown()
        super().closeEvent(event)
