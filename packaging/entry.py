# SPDX-License-Identifier: GPL-3.0-only
"""PyInstaller entrypoint. freeze_support must run before application dispatch."""
import multiprocessing

if __name__=='__main__':
    multiprocessing.freeze_support()
    from gesture_control.desktop_entry import main
    raise SystemExit(main())
