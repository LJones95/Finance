import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # SQL query finds users cash balance
    rows = db.execute("SELECT * from users WHERE id = :user_id", user_id=session["user_id"])
    cash = rows[0]["cash"]

    # SQL query groups total inputs by stock symbol and sums total shares bought for each stock
    rows = db.execute("SELECT *, SUM(shares) FROM stonks WHERE user_id = :user_id GROUP BY symbol", user_id=session["user_id"])

    # Stores latest prices for each stock in a dictionary
    latestPrices = {}

    # Stores total value of all shares
    total = 0

    for row in rows:
        latestPrices[row["symbol"]] = lookup(row["symbol"]).get("price")
        totalprice = row["SUM(shares)"] * lookup(row["symbol"]).get("price")
        total += totalprice

    return render_template("index.html", cash=cash, rows=rows, latestPrice = latestPrices, total=total)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        # Checks stock was entered
        if not request.form.get("symbol"):
            return apology("Invalid Symbol", 400)

        # Checks that stock is correct
        if lookup(request.form.get("symbol")) == None:
            return apology("Invalid Symbol", 400)

        # Checks that a share was entered
        if not request.form.get("shares"):
            return apology("missing shares", 400)

        # Checks that at least one share is entered
        if request.form.get("shares") < str(1):
            return apology("must buy at least one share", 400)

        # Checks that a numerical value was entered
        if request.form.get("shares").isnumeric() == False:
            return apology("shares must be numerical", 400)

        else:

            # Stores symbol and number of shares from form
            symbol = request.form.get("symbol")
            shares = int(request.form.get("shares"))

            # Uses API to lookup symbol price and name
            price = lookup(symbol).get("price")
            name = lookup(symbol).get('name')

            # Selects correct user balance in SQL database
            user_cash = db.execute("SELECT * from users WHERE id = :user_id", user_id=session["user_id"])

            # Checks that total share price is below or equal to total balance
            if price * shares <= user_cash[0]["cash"]:
                db.execute("INSERT INTO stonks (user_id, symbol, shares, price, name) VALUES (:user_id, :symbol, :shares, :price, :name)", user_id=session["user_id"], symbol=symbol, shares=shares, price=price, name=name)

                # Updates cash balance
                cash = user_cash[0]["cash"] - (price * shares)
                db.execute("UPDATE users SET cash = :cash WHERE id = :user_id", cash=cash, user_id=session["user_id"])

                flash('Bought!')
                return redirect("/")
            else:
                return apology("Can't afford", 400)
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    rows = db.execute("SELECT * FROM stonks WHERE user_id = :user_id", user_id=session["user_id"])
    return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        flash('You were successfully logged in!')
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":

        # Checks that user has typed in stock correctly
        if lookup(request.form.get("symbol")) == None:
            return apology("Incorrect Symbol", 400)

        else:
            # Uses API to lookup a stock
            quoted = lookup(request.form.get("symbol"))

            # Stores company name, stock and stock price
            name = quoted.get("name")
            symbol = quoted.get("symbol")
            price = quoted.get("price")

            return render_template("quoted.html", name=name, symbol=symbol, price=price)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        if not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure password was verified
        if not request.form.get("confirmation"):
            return apology("must verify password", 400)

        # Ensure passwords match
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords must match", 400)

        username = request.form.get("username")

        # Generates hash password
        password = generate_password_hash(request.form.get("confirmation"))

        # SQL query checks for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=username)

        # Returns apology if username exists, else a new account is created
        if len(rows) == 1:
            return apology("Username is not available", 400)

        db.execute("INSERT INTO users (username, hash) VALUES (:username, :password)", username=username, password=password)

        rows = db.execute("SELECT * FROM users WHERE username = :username", username=username)

        # Remember which user has registered
        session["user_id"] = rows[0]["id"]

        flash('You were successfully registered!')
        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # Gets all the user symbols from the db and groups them
    portfolio = db.execute("SELECT *, SUM(shares) FROM stonks where user_id = :user_id GROUP BY symbol", user_id=session["user_id"])

    # Checks that user picks a stock symbol
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("missing symbol", 400)

        if not request.form.get("shares"):
            return apology("missing shares", 400)

        symbol = request.form.get("symbol")
        share = int(request.form.get("shares"))
        price = lookup(symbol).get("price")
        name = lookup(symbol).get('name')

        total_shares = 0

        for row in portfolio:
            if row["symbol"] == symbol:
                total_shares = row["SUM(shares)"]


        # Gets the current amount of cash from the user and the current stock price
        user_cash = db.execute("SELECT * from users WHERE id = :user_id", user_id=session["user_id"])

        if share <= total_shares:

            # Updates the users cash
            cash = user_cash[0]["cash"] + (price * share)
            db.execute("UPDATE users SET cash = :cash WHERE id = :user_id", cash=cash, user_id=session["user_id"])

            # Updates the amount of shares
            db.execute("INSERT INTO stonks (user_id, symbol, shares, price, name) VALUES (:user_id, :symbol, :shares, :price, :name)", user_id=session["user_id"], symbol=symbol, shares=(share * -1), price=price, name=name)

        else:
            return apology("too many shares", 400)

        flash('Sold!')
        return redirect("/")
    else:
        return render_template("sell.html", portfolio=portfolio)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
