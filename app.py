from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "smart-expense-tracker-secret-key"

DATABASE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "expenses.db"
)


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


# =========================================================
# CREATE BUDGET TABLE
# =========================================================

def create_budget_table():
    connection = get_db_connection()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT UNIQUE NOT NULL,
            amount REAL NOT NULL
        )
    """)

    connection.commit()
    connection.close()


# =========================================================
# VALIDATE EXPENSE
# =========================================================

def validate_expense(amount, category, date):

    errors = []

    try:
        amount_value = float(amount)

        if amount_value <= 0:
            errors.append("Amount must be greater than 0.")

    except (ValueError, TypeError):
        errors.append("Amount must be a valid number.")

    if not category or not category.strip():
        errors.append("Category cannot be empty.")

    try:
        datetime.strptime(date, "%d-%m-%Y")
    except (ValueError, TypeError):
        errors.append("Date must be in DD-MM-YYYY format.")

    return errors


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/")
def dashboard():

    connection = get_db_connection()

    search = request.args.get("search", "").strip()

    # -----------------------------------------------------
    # EXPENSES
    # -----------------------------------------------------

    if search:

        expenses = connection.execute("""
            SELECT *
            FROM expenses
            WHERE category LIKE ?
               OR description LIKE ?
            ORDER BY id DESC
        """, (
            f"%{search}%",
            f"%{search}%"
        )).fetchall()

    else:

        expenses = connection.execute("""
            SELECT *
            FROM expenses
            ORDER BY id DESC
        """).fetchall()

    # -----------------------------------------------------
    # BASIC STATISTICS
    # -----------------------------------------------------

    total = connection.execute("""
        SELECT COALESCE(SUM(amount), 0)
        FROM expenses
    """).fetchone()[0]

    count = connection.execute("""
        SELECT COUNT(*)
        FROM expenses
    """).fetchone()[0]

    highest = connection.execute("""
        SELECT COALESCE(MAX(amount), 0)
        FROM expenses
    """).fetchone()[0]

    average = connection.execute("""
        SELECT COALESCE(AVG(amount), 0)
        FROM expenses
    """).fetchone()[0]

    # -----------------------------------------------------
    # CATEGORY DATA
    # -----------------------------------------------------

    category_data = connection.execute("""
        SELECT
            category,
            SUM(amount) AS total
        FROM expenses
        GROUP BY category
        ORDER BY total DESC
    """).fetchall()

    # -----------------------------------------------------
    # MONTHLY DATA
    # -----------------------------------------------------

    monthly_data = connection.execute("""
        SELECT
            substr(date, 4, 2) AS month,
            substr(date, 7, 4) AS year,
            SUM(amount) AS total
        FROM expenses
        GROUP BY year, month
        ORDER BY year, month
    """).fetchall()

    # -----------------------------------------------------
    # CURRENT MONTH
    # -----------------------------------------------------

    now = datetime.now()

    current_month = now.strftime("%m-%Y")
    current_month_name = now.strftime("%B %Y")

    current_month_spending = connection.execute("""
        SELECT COALESCE(SUM(amount), 0)
        FROM expenses
        WHERE substr(date, 4, 2) = ?
        AND substr(date, 7, 4) = ?
    """, (
        current_month[:2],
        current_month[3:]
    )).fetchone()[0]

    # -----------------------------------------------------
    # CURRENT MONTH BUDGET
    # -----------------------------------------------------

    budget_record = connection.execute("""
        SELECT amount
        FROM budgets
        WHERE month = ?
    """, (current_month,)).fetchone()

    if budget_record:
        budget_amount = budget_record["amount"]
    else:
        budget_amount = 0

    # -----------------------------------------------------
    # BUDGET CALCULATIONS
    # -----------------------------------------------------

    remaining_budget = budget_amount - current_month_spending

    if budget_amount > 0:

        budget_percentage = (
            current_month_spending / budget_amount
        ) * 100

    else:

        budget_percentage = 0

    progress_percentage = min(
        max(budget_percentage, 0),
        100
    )

    # -----------------------------------------------------
    # BUDGET ALERT
    # -----------------------------------------------------

    if budget_amount == 0:

        budget_status = "No Budget Set"
        budget_status_class = "neutral"

    elif current_month_spending > budget_amount:

        budget_status = "Budget Exceeded"
        budget_status_class = "danger"

    elif budget_percentage >= 80:

        budget_status = "Almost at Budget Limit"
        budget_status_class = "warning"

    else:

        budget_status = "Within Budget"
        budget_status_class = "success"

    # -----------------------------------------------------
    # EXPENSE INSIGHTS
    # -----------------------------------------------------

    if category_data:

        highest_category = category_data[0]["category"]
        highest_category_amount = category_data[0]["total"]

    else:

        highest_category = "No data"
        highest_category_amount = 0

    if total > 0:

        highest_category_percentage = (
            highest_category_amount / total
        ) * 100

    else:

        highest_category_percentage = 0

    # -----------------------------------------------------
    # AVERAGE DAILY EXPENSE
    # -----------------------------------------------------

    unique_days = connection.execute("""
        SELECT COUNT(DISTINCT date)
        FROM expenses
    """).fetchone()[0]

    if unique_days > 0:
        average_daily = total / unique_days
    else:
        average_daily = 0

    # -----------------------------------------------------
    # BIGGEST TRANSACTION
    # -----------------------------------------------------

    biggest_expense = connection.execute("""
        SELECT *
        FROM expenses
        ORDER BY amount DESC
        LIMIT 1
    """).fetchone()

    # -----------------------------------------------------
    # CURRENT MONTH EXPENSE COUNT
    # -----------------------------------------------------

    current_month_count = connection.execute("""
        SELECT COUNT(*)
        FROM expenses
        WHERE substr(date, 4, 2) = ?
        AND substr(date, 7, 4) = ?
    """, (
        current_month[:2],
        current_month[3:]
    )).fetchone()[0]

    connection.close()

    # -----------------------------------------------------
    # SEND DATA TO HTML
    # -----------------------------------------------------

    return render_template(
        "index.html",

        expenses=expenses,

        total=total,
        count=count,
        highest=highest,
        average=average,

        category_data=category_data,
        monthly_data=monthly_data,

        search=search,

        current_month=current_month,
        current_month_name=current_month_name,

        budget_amount=budget_amount,
        current_month_spending=current_month_spending,
        remaining_budget=remaining_budget,

        budget_percentage=budget_percentage,
        progress_percentage=progress_percentage,

        budget_status=budget_status,
        budget_status_class=budget_status_class,

        highest_category=highest_category,
        highest_category_amount=highest_category_amount,
        highest_category_percentage=highest_category_percentage,

        average_daily=average_daily,

        biggest_expense=biggest_expense,

        current_month_count=current_month_count
    )


# =========================================================
# ADD EXPENSE
# =========================================================

@app.route("/add", methods=["GET", "POST"])
def add_expense():

    if request.method == "POST":

        amount = request.form.get("amount", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        date = request.form.get("date", "").strip()

        errors = validate_expense(
            amount,
            category,
            date
        )

        if errors:

            return render_template(
                "add.html",
                errors=errors,
                amount=amount,
                category=category,
                description=description,
                date=date
            )

        connection = get_db_connection()

        connection.execute("""
            INSERT INTO expenses
            (
                amount,
                category,
                description,
                date
            )
            VALUES (?, ?, ?, ?)
        """, (
            float(amount),
            category,
            description,
            date
        ))

        connection.commit()
        connection.close()

        flash(
            "Expense added successfully!",
            "success"
        )

        return redirect(
            url_for("dashboard")
        )

    return render_template("add.html")


# =========================================================
# EDIT EXPENSE
# =========================================================

@app.route("/edit/<int:expense_id>", methods=["GET", "POST"])
def edit_expense(expense_id):

    connection = get_db_connection()

    expense = connection.execute("""
        SELECT *
        FROM expenses
        WHERE id = ?
    """, (expense_id,)).fetchone()

    if expense is None:

        connection.close()

        return "Expense not found", 404

    if request.method == "POST":

        amount = request.form.get("amount", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        date = request.form.get("date", "").strip()

        errors = validate_expense(
            amount,
            category,
            date
        )

        if errors:

            connection.close()

            return render_template(
                "edit.html",

                expense=expense,

                errors=errors,

                amount=amount,
                category=category,
                description=description,
                date=date
            )

        connection.execute("""
            UPDATE expenses
            SET
                amount = ?,
                category = ?,
                description = ?,
                date = ?
            WHERE id = ?
        """, (
            float(amount),
            category,
            description,
            date,
            expense_id
        ))

        connection.commit()
        connection.close()

        flash(
            "Expense updated successfully!",
            "success"
        )

        return redirect(
            url_for("dashboard")
        )

    connection.close()

    return render_template(
        "edit.html",
        expense=expense
    )


# =========================================================
# DELETE EXPENSE
# =========================================================

@app.route("/delete/<int:expense_id>")
def delete_expense(expense_id):

    connection = get_db_connection()

    expense = connection.execute("""
        SELECT *
        FROM expenses
        WHERE id = ?
    """, (expense_id,)).fetchone()

    if expense is None:

        connection.close()

        return "Expense not found", 404

    connection.execute("""
        DELETE FROM expenses
        WHERE id = ?
    """, (expense_id,))

    connection.commit()
    connection.close()

    flash(
        "Expense deleted successfully!",
        "success"
    )

    return redirect(
        url_for("dashboard")
    )


# =========================================================
# BUDGET PLANNER
# =========================================================

@app.route("/budget", methods=["GET", "POST"])
def budget():

    connection = get_db_connection()

    current_month = datetime.now().strftime("%m-%Y")
    current_month_name = datetime.now().strftime("%B %Y")

    # -----------------------------------------------------
    # SAVE / UPDATE BUDGET
    # -----------------------------------------------------

    if request.method == "POST":

        budget_amount = request.form.get(
            "budget_amount",
            ""
        ).strip()

        try:

            budget_value = float(budget_amount)

            if budget_value <= 0:

                flash(
                    "Budget must be greater than 0.",
                    "error"
                )

                connection.close()

                return redirect(
                    url_for("budget")
                )

        except (ValueError, TypeError):

            flash(
                "Please enter a valid budget amount.",
                "error"
            )

            connection.close()

            return redirect(
                url_for("budget")
            )

        existing_budget = connection.execute("""
            SELECT *
            FROM budgets
            WHERE month = ?
        """, (current_month,)).fetchone()

        if existing_budget:

            connection.execute("""
                UPDATE budgets
                SET amount = ?
                WHERE month = ?
            """, (
                budget_value,
                current_month
            ))

            message = "Monthly budget updated successfully!"

        else:

            connection.execute("""
                INSERT INTO budgets
                (
                    month,
                    amount
                )
                VALUES (?, ?)
            """, (
                current_month,
                budget_value
            ))

            message = "Monthly budget set successfully!"

        connection.commit()
        connection.close()

        flash(
            message,
            "success"
        )

        return redirect(
            url_for("budget")
        )

    # -----------------------------------------------------
    # GET CURRENT BUDGET
    # -----------------------------------------------------

    budget_record = connection.execute("""
        SELECT amount
        FROM budgets
        WHERE month = ?
    """, (current_month,)).fetchone()

    if budget_record:
        budget_amount = budget_record["amount"]
    else:
        budget_amount = 0

    # -----------------------------------------------------
    # CURRENT MONTH SPENDING
    # -----------------------------------------------------

    current_month_spending = connection.execute("""
        SELECT COALESCE(SUM(amount), 0)
        FROM expenses
        WHERE substr(date, 4, 2) = ?
        AND substr(date, 7, 4) = ?
    """, (
        current_month[:2],
        current_month[3:]
    )).fetchone()[0]

    connection.close()

    # -----------------------------------------------------
    # CALCULATIONS
    # -----------------------------------------------------

    remaining = budget_amount - current_month_spending

    if budget_amount > 0:

        percentage = (
            current_month_spending /
            budget_amount
        ) * 100

    else:

        percentage = 0

    progress_percentage = min(
        max(percentage, 0),
        100
    )

    # -----------------------------------------------------
    # STATUS
    # -----------------------------------------------------

    if budget_amount == 0:

        status = "No Budget Set"
        status_class = "neutral"

    elif current_month_spending > budget_amount:

        status = "Budget Exceeded"
        status_class = "danger"

    elif percentage >= 80:

        status = "Almost at Budget Limit"
        status_class = "warning"

    else:

        status = "Within Budget"
        status_class = "success"

    # -----------------------------------------------------
    # OPEN budget.html
    # -----------------------------------------------------

    return render_template(
        "budget.html",

        current_month=current_month,
        current_month_name=current_month_name,

        budget_amount=budget_amount,

        current_month_spending=current_month_spending,

        remaining=remaining,

        percentage=percentage,

        progress_percentage=progress_percentage,

        status=status,

        status_class=status_class
    )


# =========================================================
# START APPLICATION
# =========================================================

if __name__ == "__main__":

    create_budget_table()

    app.run(
        debug=True
    )