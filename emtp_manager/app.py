"""Application entry point for the EMTP Data Manager."""

import tkinter as tk

from emtp_manager.ui.shell import MainWindow


def main() -> None:
    root = tk.Tk()
    MainWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
