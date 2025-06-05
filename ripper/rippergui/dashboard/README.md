# Financial Dashboard for Ripper

A powerful, customizable financial dashboard system for visualizing and analyzing Tiller financial data.

## Features

- **Visual Dashboard Builder**: Drag-and-drop interface for building custom dashboards
- **Multiple Widget Types**: Various financial visualization widgets including:
  - Spending trends
  - Category breakdowns
  - Budget vs. actual comparisons
  - Top expenses
  - Net worth tracking
  - Savings goals
  - Income vs. expense analysis
- **Data Source Management**: Connect to Tiller spreadsheets
- **Customizable Layouts**: Resize and arrange widgets as needed
- **Responsive Design**: Works on different screen sizes

## Getting Started

### Prerequisites

- Python 3.8+
- PySide6
- pandas
- Other dependencies from requirements.txt

### Installation

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

### Running the Application

To start the financial dashboard:

```bash
python -m ripper.rippergui.dashboard
```

## Usage

### Creating a New Dashboard

1. Click "New Dashboard" in the toolbar
2. Give your dashboard a name and description
3. Add widgets using the widget palette
4. Configure each widget's data source and appearance
5. Save your dashboard

### Adding Widgets

1. Click and drag a widget from the palette to the dashboard
2. Resize and position the widget as needed
3. Configure the widget's data source and settings

### Configuring Data Sources

1. Click the "Edit" button to enter edit mode
2. Click on a widget to select it
3. In the properties panel, configure the data source:
   - Select a Tiller spreadsheet
   - Choose date ranges
   - Apply filters (accounts, categories, etc.)

## Widget Reference

### Spending Trend

Shows a line chart of spending over time.

**Configuration Options:**
- Date range
- Accounts to include
- Categories to include
- Line style and color

### Category Breakdown

Displays a pie chart of spending by category.

**Configuration Options:**
- Date range
- Accounts to include
- Categories to include
- Color scheme

### Budget vs. Actual

Compares budgeted amounts to actual spending.

**Configuration Options:**
- Date range
- Categories to include
- Bar colors

### Top Expenses

Shows a table of the largest expenses.

**Configuration Options:**
- Date range
- Number of expenses to show
- Columns to display

## Keyboard Shortcuts

- **Ctrl+N**: New dashboard
- **Ctrl+O**: Open dashboard
- **Ctrl+S**: Save dashboard
- **Ctrl+E**: Toggle edit mode
- **F5**: Refresh data

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
