# Ripper

This project is a PySide6 application that authenticates over OAuth to import bank transaction data from a Google Sheet populated by Tiller Finance. The transactions are then displayed in a sortable, filterable table.

## Setup

1. Clone the repository:
   ```
   git clone https://github.com/solarisin/ripper.git
   cd ripper
   ```

## Running the Project

1. Run the application:
   ```
   ./start_ripper.sh
   ```

2. Follow the instructions in the application to authenticate with your Google account and import the bank transaction data from the Google Sheet.
   - After the first login, you will be prompted to configure where to pull transaction data from.
   - Use the file picker dialog to select the Google Sheet directly from your Google Drive.
   - The selected data source configuration will be stored in the SQLite database.

3. The transactions will be displayed in a sortable, filterable table in the PySide6 application.
