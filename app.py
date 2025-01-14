from datetime import datetime
import mysql.connector
from decimal import Decimal
from flask import Flask, render_template, request, redirect, url_for, session
import hashlib

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# MySQL database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',  # Replace with your MySQL username
    'password': '4560',  # Replace with your MySQL password
    'database': 'banksystem'
}
# Helper function to get a database connection
def get_db_connection():
    return mysql.connector.connect(**db_config)

# Example of using a simple hashing algorithm (SHA256) and truncating the hash
def generate_short_hash(password):
    # Using SHA256 for this example
    hashed = hashlib.sha256(password.encode('utf-8')).hexdigest() 
    # Truncate to the first 16 characters (for example)
    short_hash = hashed[:16]  # This is not secure, just for demonstration
    return short_hash

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/signup')
def signup():
    return render_template('signup.html')

@app.route('/register', methods=['POST'])
def register():
    name = request.form['name']
    email = request.form['email']
    userid = request.form['userid']
    password = request.form['password']
    branch = request.form['branch']
    account_type = request.form['account_type']

    # Generate a short hashed password
    hashed_password = generate_short_hash(password)

    # Insert user and account details into the database
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Insert user data
        cursor.execute(
            "INSERT INTO users (name, email, user_id, password) VALUES (%s, %s, %s, %s)",
            (name, email, userid, hashed_password)
        )
        # Insert account data
        cursor.execute(
            "INSERT INTO accounts (account_no, account_type, balance, branch, user_id) VALUES (%s, %s, %s, %s, %s)",
            (f"{len(userid)}{datetime.now().strftime('%H%M%S')}", account_type, 10000, branch, userid)
        )
        connection.commit()
    except Exception as e:
        connection.rollback()
        return f"Error: {str(e)}"
    finally:
        cursor.close()
        connection.close()
    return render_template('account.html', name=name)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        userid = request.form['userid']
        password = request.form['password']

        # Generate the short hash for the entered password
        hashed_password = generate_short_hash(password)

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE user_id = %s AND password = %s", (userid, hashed_password))
        user = cursor.fetchone()
        cursor.close()
        connection.close()

        if user:
            session['user'] = user['user_id']
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', message="Invalid credentials. Please try again.")

    return render_template('login.html', message=None)

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    userid = session['user']
    
    # Fetch user details from the database
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Query user details
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (userid,))
    user = cursor.fetchone()
    
    # Query account details
    cursor.execute("SELECT * FROM accounts WHERE user_id = %s", (userid,))
    account = cursor.fetchone()
    
    cursor.close()
    connection.close()
    
    if not user or not account:
        return "Error: User or account details not found."
    
    # Pass user and account details to the template
    return render_template(
        'dashboard.html',
        name=user['name'],
        account_number=account['account_no'],
        branch=account['branch'],
        balance=account['balance']
    )

@app.route('/deposit', methods=['GET', 'POST'])
def deposit():
    if 'user' not in session:
        return redirect(url_for('login'))
    user_id = session['user']
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("""
        SELECT accounts.account_no, accounts.balance, users.name 
        FROM accounts 
        INNER JOIN users ON accounts.user_id = users.user_id
        WHERE accounts.user_id = %s
    """, (user_id,))
    user_data = cursor.fetchone()

    if not user_data:
        return render_template('deposit.html', message="User data not found. Please contact support.")

    if request.method == 'POST':
        try:
            # Get and validate the deposit amount
            amount = Decimal(request.form.get('amount', '0'))
            if amount <= 0:
                raise ValueError("Please enter a positive amount.")

            # Update balance and insert transaction
            new_balance = user_data['balance'] + amount
            cursor.execute("UPDATE accounts SET balance = %s WHERE account_no = %s", 
                           (new_balance, user_data['account_no']))
            connection.commit()  # Commit after updating balance
            
            # Insert transaction into the database
            cursor.execute("""
                INSERT INTO transactions (account_no, transaction_type, amount, date_time, balance, details) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                user_data['account_no'],
                'Deposit',
                amount,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                new_balance,
                'Deposit made by user'
            ))

            connection.commit()

            message = f"Successfully deposited ₹{amount}. Current balance is ₹{new_balance:.2f}"

        except mysql.connector.Error as e:
            # Specific MySQL error handling
            print(f"MySQL error: {e}")
            connection.rollback()  # Rollback if there was a MySQL error
            message = f"An error occurred: {str(e)}"

        except (ValueError, TypeError) as e:
            # Value or Type error handling
            message = str(e)

        except Exception as e:
            # General error handling
            print(f"Error occurred: {e}")
            connection.rollback()
            message = f"An error occurred: {str(e)}"

        return render_template('deposit.html', 
                               name=user_data['name'],
                               account_number=user_data['account_no'],
                               balance=new_balance, 
                               message=message)

    return render_template('deposit.html', 
                           name=user_data['name'],
                           account_number=user_data['account_no'],
                           balance=user_data['balance'], 
                           message=None)


@app.route('/withdraw', methods=['GET', 'POST'])
def withdraw():
    if 'user' not in session:
        return redirect(url_for('login'))

    user_id = session['user']
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("""
        SELECT accounts.account_no, accounts.balance, users.name 
        FROM accounts 
        INNER JOIN users ON accounts.user_id = users.user_id
        WHERE accounts.user_id = %s
    """, (user_id,))
    user_data = cursor.fetchone()

    if not user_data:
        return render_template('withdraw.html', message="User data not found. Please contact support.")

    if request.method == 'POST':
        try:
            amount = Decimal(request.form.get('amount', '0'))
            if amount <= 0:
                raise ValueError("Please enter a positive amount.")

            # Update balance and insert transaction
            new_balance = user_data['balance'] - amount
            cursor.execute("UPDATE accounts SET balance = %s WHERE account_no = %s", 
                           (new_balance, user_data['account_no']))
            connection.commit()

            # Insert transaction into the database
            cursor.execute("""
                INSERT INTO transactions (account_no, transaction_type, amount, date_time, balance, details) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                user_data['account_no'],
                'Withdrawal',
                amount,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                new_balance,
                'Withdrawal made by user'
            ))

            connection.commit()

            message = f"Successful withdrawal of ₹{amount}. Current balance is ₹{new_balance:.2f}"

        except mysql.connector.Error as e:
            # Specific MySQL error handling
            print(f"MySQL error: {e}")
            connection.rollback()
            message = f"An error occurred: {str(e)}"

        except (ValueError, TypeError) as e:
            message = str(e)

        except Exception as e:
            # General error handling
            print(f"Error occurred: {e}")
            connection.rollback()
            message = f"An error occurred: {str(e)}"

        return render_template('withdraw.html', 
                               name=user_data['name'],
                               account_number=user_data['account_no'],
                               balance=new_balance, 
                               message=message)

    return render_template('withdraw.html', 
                           name=user_data['name'],
                           account_number=user_data['account_no'],
                           balance=user_data['balance'], 
                           message=None)


@app.route('/transaction-history', methods=['GET'])
def transaction_history():
    if 'user' not in session:
        return redirect(url_for('login'))
    user_id = session['user']  # Fetch the logged-in user ID
    try:
        # Establish database connection
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        # Fetch the account details for the logged-in user
        cursor.execute("SELECT * FROM accounts WHERE user_id = %s", (user_id,))
        account_info = cursor.fetchone()
        
        if not account_info:
            print(f"No account found for user_id: {user_id}")
            return "Error: Account information not found."
        # Fetch the transaction history for the user's account
        cursor.execute(""" 
            SELECT transaction_type, amount, date_time, balance, details 
            FROM transactions 
            WHERE account_no = %s 
            ORDER BY date_time DESC
        """, (account_info['account_no'],))
        transaction_history = cursor.fetchall()
        if not transaction_history:
            print(f"No transactions found for account_no: {account_info['account_no']}")
            transaction_history = []  # Empty list if no transactions exist
        # Close the cursor and connection
        cursor.close()
        connection.close()
        # Render the transaction history template with the fetched data
        return render_template(
            'transaction_history.html',
            transactions=transaction_history,
            name=account_info['user_id'],  # Or use any relevant user info
            account_number=account_info['account_no']
        )
    except mysql.connector.Error as db_error:
        print(f"MySQL error: {db_error}")
        return "An error occurred while fetching transaction history."
    except Exception as e:
        print(f"General error: {e}")
        return "An unexpected error occurred."

@app.route('/transfer', methods=['GET', 'POST'])
def transfer():
    if 'user' not in session:
        return redirect(url_for('login'))

    userid = session['user']

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    if request.method == 'POST':
        recipient_account_number = request.form['recipient_account_number']
        amount = request.form.get('amount')

        try:
            # Convert amount to Decimal for consistency
            amount = Decimal(amount)

            if amount <= 0:
                return render_template('transfer.html', message="Please enter a valid amount.")

            # Get sender details
            cursor.execute("SELECT account_no, balance FROM accounts WHERE user_id = %s", (userid,))
            sender = cursor.fetchone()

            if sender['balance'] < amount:
                return render_template('transfer.html', message="Insufficient balance.")

            # Get recipient details
            cursor.execute("SELECT * FROM accounts WHERE account_no = %s", (recipient_account_number,))
            recipient = cursor.fetchone()

            if not recipient:
                return render_template('transfer.html', message="Recipient account not found.")

            # Update balances
            sender_new_balance = sender['balance'] - amount
            recipient_new_balance = recipient['balance'] + amount

            cursor.execute("UPDATE accounts SET balance = %s WHERE account_no = %s", (sender_new_balance, sender['account_no']))
            cursor.execute("UPDATE accounts SET balance = %s WHERE account_no = %s", (recipient_new_balance, recipient_account_number))

            # Record transactions
            cursor.execute(
                "INSERT INTO transactions (account_no, date_time, transaction_type, amount, details, balance) VALUES (%s, %s, %s, %s, %s, %s)",
                (sender['account_no'], datetime.now(), 'Transfer Sent', amount, f"To {recipient_account_number}", sender_new_balance)
            )
            cursor.execute(
                "INSERT INTO transactions (account_no, date_time, transaction_type, amount, details, balance) VALUES (%s, %s, %s, %s, %s, %s)",
                (recipient['account_no'], datetime.now(), 'Transfer Received', amount, f"From {sender['account_no']}", recipient_new_balance)
            )

            connection.commit()

            return render_template('transfer.html', message="Transfer successful!")

        except mysql.connector.Error as e:
            print(f"MySQL error: {e}")
            connection.rollback()  # Rollback transaction on error
            return render_template('transfer.html', message=f"Error: {str(e)}")

        except Exception as e:
            print(f"Error: {e}")
            connection.rollback()
            return render_template('transfer.html', message=f"Error: {str(e)}")

    return render_template('transfer.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)


