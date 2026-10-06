"""Lanzador de OCT Workbench. Ejecutar desde cualquier directorio."""

import sys

from PyQt5.QtWidgets import QApplication
from gui.main_window import MainWindow, configure_numeric_locale


def main():
    configure_numeric_locale()
    app = QApplication(sys.argv)
    app.setApplicationName("OCT Workbench")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
