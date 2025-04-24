import sqlite3
from sqlite3 import Error
from cryptography.fernet import Fernet
import os

DATABASE_FILE = 'transactions.db'
ENCRYPTION_KEY_FILE = 'encryption.key'

def create_connection():
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
    except Error as e:
        print(e)
    return conn

def create_table():
    conn = create_connection()
    if conn is not None:
        try:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                            id INTEGER PRIMARY KEY,
                            date TEXT NOT NULL,
                            description TEXT NOT NULL,
                            amount REAL NOT NULL,
                            category TEXT NOT NULL
                        );''')
            c.execute('''CREATE TABLE IF NOT EXISTS data_sources (
                            id INTEGER PRIMARY KEY,
                            spreadsheet_id TEXT NOT NULL,
                            range_name TEXT NOT NULL
                        );''')
            c.execute('''CREATE TABLE IF NOT EXISTS login_attempts (
                            id INTEGER PRIMARY KEY,
                            timestamp TEXT NOT NULL,
                            success INTEGER NOT NULL
                        );''')
            conn.commit()
        except Error as e:
            print(e)
        finally:
            conn.close()

def insert_transaction(transaction):
    conn = create_connection()
    if conn is not None:
        try:
            c = conn.cursor()
            c.execute('''INSERT INTO transactions (date, description, amount, category)
                         VALUES (?, ?, ?, ?)''', (transaction['date'], transaction['description'], transaction['amount'], transaction['category']))
            conn.commit()
        except Error as e:
            print(e)
        finally:
            conn.close()

def retrieve_transactions():
    conn = create_connection()
    transactions = []
    if conn is not None:
        try:
            c = conn.cursor()
            c.execute('SELECT * FROM transactions')
            rows = c.fetchall()
            for row in rows:
                transaction = {
                    'date': row[1],
                    'description': row[2],
                    'amount': row[3],
                    'category': row[4]
                }
                transactions.append(transaction)
        except Error as e:
            print(e)
        finally:
            conn.close()
    return transactions

def insert_data_source(spreadsheet_id, range_name):
    conn = create_connection()
    if conn is not None:
        try:
            c = conn.cursor()
            c.execute('''INSERT INTO data_sources (spreadsheet_id, range_name)
                         VALUES (?, ?)''', (spreadsheet_id, range_name))
            conn.commit()
        except Error as e:
            print(e)
        finally:
            conn.close()

def insert_login_attempt(success):
    conn = create_connection()
    if conn is not None:
        try:
            c = conn.cursor()
            c.execute('''INSERT INTO login_attempts (timestamp, success)
                         VALUES (datetime('now'), ?)''', (1 if success else 0,))
            conn.commit()
        except Error as e:
            print(e)
        finally:
            conn.close()

def generate_encryption_key():
    key = Fernet.generate_key()
    with open(ENCRYPTION_KEY_FILE, 'wb') as key_file:
        key_file.write(key)

def load_encryption_key():
    return open(ENCRYPTION_KEY_FILE, 'rb').read()

def encrypt_database():
    key = load_encryption_key()
    fernet = Fernet(key)
    with open(DATABASE_FILE, 'rb') as file:
        original = file.read()
    encrypted = fernet.encrypt(original)
    with open(DATABASE_FILE, 'wb') as encrypted_file:
        encrypted_file.write(encrypted)

def decrypt_database():
    key = load_encryption_key()
    fernet = Fernet(key)
    with open(DATABASE_FILE, 'rb') as file:
        encrypted = file.read()
    decrypted = fernet.decrypt(encrypted)
    with open(DATABASE_FILE, 'wb') as decrypted_file:
        decrypted_file.write(decrypted)

if not os.path.exists(ENCRYPTION_KEY_FILE):
    generate_encryption_key()
create_table()
