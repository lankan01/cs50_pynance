import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from helpers import apology, login_required, lookup, usd
from werkzeug.security import check_password_hash, generate_password_hash


# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    user_id = session["user_id"]

    # Get all distinct symbols owned by the user
    owned_symbols = db.execute("SELECT DISTINCT(symbol) FROM transactions WHERE user_id = ? GROUP BY symbol HAVING SUM(shares) > 0", user_id)

    if not owned_symbols:
        return render_template("no_symbols.html")  # or redirect to another appropriate page

    all_stocks = []

    for symbol_data in owned_symbols:
        symbol = symbol_data['symbol']

        # Get total shares for the symbol
        owned_shares = db.execute("SELECT SUM(shares) FROM transactions WHERE user_id = ? AND symbol = ?", user_id, symbol)[0]['SUM(shares)']

        # Get current stock price
        stock_info = lookup(symbol)
        stock_price = stock_info['price']

        # Fetch purchase prices for the symbol
        bought_list = db.execute("SELECT price FROM transactions WHERE user_id = ? AND symbol = ?", user_id, symbol)

        # Calculate the % change in stock price since the user bought it
        total_percen_change = 0
        for bought_data in bought_list:
            bought_price = bought_data.get('price', 0)
            percen = round((stock_price - bought_price) / bought_price * 100, 2) if bought_price else 0
            total_percen_change += percen
        print(total_percen_change)

        stock_dict = {
        'symbol': symbol,
        'price': stock_price,
        'owned_shares': owned_shares,
        'percen_change': total_percen_change
    }
        all_stocks.append(stock_dict)


    # Get user's balance
    user_balance = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]['cash']
    user_balance = "{:.2f}".format(user_balance)

    return render_template("index.html",
                           all_stocks=all_stocks,
                           user_balance=user_balance)



@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == 'POST':

        if not (symbol := request.form.get("symbol").upper()):
            return apology("MISSING SYMBOL")

        if not (shares := request.form.get("shares")):
            return apology("MISSING SHARES")

        # Check share is numeric data type
        try:
            shares = int(shares)
        except ValueError:
            return apology("INVALID SHARES")

        # Check shares is positive number
        if not (shares > 0):
            return apology("INVALID SHARES")

        # Ensure symbol is valided
        if not (quote := lookup(symbol)):
            return apology("INVALID SYMBOL")

        quote_price = quote["price"]
        user_balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

        if user_balance < quote_price * shares:
            return apology("Not enough money", 400)
        # insert into transactions
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)", session["user_id"], symbol, shares, quote_price)
        # update cash
        db.execute("UPDATE users SET cash = ? WHERE id = ?", user_balance - quote_price * shares, session["user_id"])
        # redirect to index
        flash("Successfully bought")
        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    transactions = db.execute("SELECT * FROM transactions WHERE user_id = ?", session["user_id"])
    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
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
    if request.method == 'POST':
        symbol = request.form.get("symbol").upper()
        quote = lookup(symbol)
        print(quote)
        shares = db.execute("SELECT sum(shares) FROM transactions WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)[0]["sum(shares)"]
        print(shares)
        if not quote or quote == None:
            return apology("Invalid ticker", 400)
        else:
            return render_template("quoted.html", quote=quote, shares=shares)
    else:
        return render_template("quotes.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == 'POST':
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not username:
            return apology("Must provide username", 400)

        if not password:
            return apology("Must provide password", 400)

        if password != confirmation:
            return apology("Passwords do not match", 400)

        hash = generate_password_hash(password)

        existing_user = db.execute("SELECT * FROM users WHERE username = ?", username)
        # success:
        if existing_user:
            return apology("Username already exists :(")
        else:
            db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, hash)
            return redirect("/login")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares_entry = request.form.get("shares")
        if shares_entry == "" or int(shares_entry) <= 0:
            return apology("Invalid shares")
        else:
            sell_shares = int(shares_entry)

        quote = lookup(symbol)
        quote_price = quote["price"]

        if quote == None:
            return apology("Invalid ticker")

        # check if user has enough shares
        shares_owned = db.execute("SELECT SUM(shares) FROM transactions WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)[0]["SUM(shares)"]

        user_balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

        if sell_shares > shares_owned:
            return apology("Not enough shares")
        else:
            sell_shares = sell_shares * -1
            db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)", session["user_id"], symbol, sell_shares, quote_price)
            db.execute("UPDATE users SET cash = ? WHERE id = ?", user_balance - quote_price * sell_shares, session["user_id"])

            flash("Successfully sold")
            return redirect("/")

    else:
        user_id = session["user_id"]
        symbols_owned = db.execute("SELECT DISTINCT symbol FROM transactions WHERE user_id = ? GROUP BY symbol HAVING SUM(shares) > 0", user_id)
        symbols_list = [item['symbol'] for item in symbols_owned]

        print(symbols_list)

        return render_template("sell.html", symbols_list=symbols_list)
