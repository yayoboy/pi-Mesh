"""`python -m gui` entrypoint.

Per ora delega allo smoke test della Fase 0. Verrà sostituito in Task 1.5
quando arriva la MainWindow vera.
"""

from gui._smoke import main


if __name__ == "__main__":
    raise SystemExit(main())
