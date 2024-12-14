from PySide6.QtCore import QMetaObject
from PySide6.QtUiTools import QUiLoader


class UiLoaderError(Exception):
    pass


class UiLoader(QUiLoader):

    def __init__(self, base, custom_widgets=None):
        QUiLoader.__init__(self, base)
        self.base = base
        self.custom_widgets = custom_widgets

    def createWidget(self, class_name, parent=None, name=""):
        if parent is None and self.base:
            return self.base
        else:
            if class_name in self.availableWidgets():
                widget = QUiLoader.createWidget(self, class_name, parent, name)
            else:
                try:
                    widget = self.custom_widgets[class_name](parent)
                except (TypeError, KeyError):
                    raise UiLoaderError(
                        f'No custom widget "{class_name}" found.'
                    )
            if self.base:
                setattr(self.base, name, widget)
            return widget


def loadUi(ui_file, base=None, custom_widgets=None, working_directory=None):
    loader = UiLoader(base, custom_widgets)
    if working_directory is not None:
        loader.setWorkingDirectory(working_directory)
    if not isinstance(ui_file, str):
        ui_file = str(ui_file)
    widget = loader.load(ui_file)
    QMetaObject.connectSlotsByName(widget)
    return widget
