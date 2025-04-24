# Ripper

This project is a PySide6 application that authenticates over OAuth to import bank transaction data from a Google Sheet populated by Tiller Finance. The transactions are then displayed in a sortable, filterable table.

## Setup

1. Clone the repository:
   ```
   git clone https://github.com/solarisin/ripper.git
   cd ripper
   ```

2. Create a virtual environment and activate it:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
   ```

3. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Register the application with Google API Console and obtain the client ID and client secret. Save the JSON file containing the client ID and client secret in the project directory.

5. Configure the SQLite database:
   - The database file will be created automatically when you run the application for the first time.
   - Ensure the database is encrypted by generating an encryption key:
     ```
     python -c "from database import generate_encryption_key; generate_encryption_key()"
     ```

## Running the Project

1. Run the application:
   ```
   python main.py
   ```

2. Follow the instructions in the application to authenticate with your Google account and import the bank transaction data from the Google Sheet.

3. The transactions will be displayed in a sortable, filterable table in the PySide6 application.

4. Configure the data source:
   - After the first login, you will be prompted to configure where to pull transaction data from.
   - Use the file picker dialog to select the Google Sheet directly from your Google Drive.
   - The selected data source configuration will be stored in the SQLite database.
