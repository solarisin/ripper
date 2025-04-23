# Bank Transaction Data Importer

This project is a PySide6 application that authenticates over OAuth to import bank transaction data from a Google Sheet populated by Tiller Finance. The transactions are then displayed in a sortable, filterable table.

## Setup

1. Clone the repository:
   ```
   git clone https://github.com/githubnext/workspace-blank.git
   cd workspace-blank
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

## Running the Project

1. Run the application:
   ```
   python main.py
   ```

2. Follow the instructions in the application to authenticate with your Google account and import the bank transaction data from the Google Sheet.

3. The transactions will be displayed in a sortable, filterable table in the PySide6 application.
