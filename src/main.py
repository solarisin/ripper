import sys
import logging
import toml
from src.auth import create_sheets_service, create_drive_service
from src.sheets_backend import read_data_from_spreadsheet, list_sheets
import importlib.metadata
from pathlib import Path
from src.widgets.mainview import MainView
from PySide6.QtWidgets import QApplication


project_path = Path(__file__).parent.parent.resolve()



def get_version():
    try:
        version = importlib.metadata.version('ProjectName')
        return version
    except importlib.metadata.PackageNotFoundError:
        pass
    pyproject_toml = toml.load(str(project_path / 'pyproject.toml'))
    return pyproject_toml['project']['version']


def test_service_creation():
    drive_service = create_drive_service()
    if not drive_service:
        logging.error('No drive service')
        return
    logging.info('Drive service created')

    sheets = list_sheets(drive_service)

    sheets_service = create_sheets_service()
    if not sheets_service:
        logging.error('No sheets service')
        return
    logging.info('Sheets service created')


def main_gui():
    logging.info(f"Starting ripper v{get_version()}")
    # test_service_creation()
    app = QApplication(sys.argv)
    main_view = MainView()
    main_view.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    # TODO add logging levels to configuration
    logging.basicConfig(level=logging.DEBUG)
    main_gui()
