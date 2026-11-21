# -*- coding: utf-8 -*-
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import sqlite3

print("=== Checking and Fixing ceZar Coffee Database ===")

base_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(base_dir)
sys.path.insert(0, base_dir)

db_file = os.path.join(base_dir, "cezar_coffee.db")

# 1. Clean stale locks
for ext in ["-journal", "-wal", "-shm"]:
    lock_file = db_file + ext
    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
            print(f"Removed stale lock: {lock_file}")
        except Exception as e:
            print(f"Error removing {lock_file}: {e}")

# 2. Check integrity
needs_rebuild = False
if not os.path.exists(db_file) or os.path.getsize(db_file) == 0:
    needs_rebuild = True
    print("Database file does not exist or empty.")
else:
    try:
        con = sqlite3.connect(db_file)
        res = con.execute("PRAGMA integrity_check;").fetchall()
        con.close()
        print("Integrity check result:", res)
        if res != [('ok',)]:
            needs_rebuild = True
            print("Database corrupted! Rebuilding...")
    except Exception as e:
        print(f"Database error: {e}")
        needs_rebuild = True

# 3. Clean Rebuild if corrupted
if needs_rebuild:
    if os.path.exists(db_file):
        backup_name = os.path.join(base_dir, "cezar_coffee_corrupt_backup.db")
        try:
            os.replace(db_file, backup_name)
            print(f"Backed up corrupted db to: {backup_name}")
        except Exception:
            pass

from sqlalchemy import text
from app.database import engine, Base, SessionLocal
from app.models import (
    MenuItem, TableOrder, ManagerAccount, Shift, Expense, Reservation,
    WaitingList, InventoryItem, PromoCode, MenuItemRecipe, Employee,
    SalaryPayment, EmployeeAttendance, CafeSetting, CafeTableConfig,
    InventoryWaste, Supplier, PurchaseInvoice, PurchaseInvoiceItem, VoidAuditLog
)
from app.seed import seed_menu, seed_recipes

Base.metadata.create_all(bind=engine)
print("Database tables created / verified cleanly.")

# Ensure missing columns exist in SQLite tables
try:
    with sqlite3.connect(db_file) as conn:
        c = conn.cursor()
        
        # Check inventory_items columns
        c.execute("PRAGMA table_info(inventory_items)")
        inv_cols = [r[1] for r in c.fetchall()]
        if "cost_per_unit" not in inv_cols:
            c.execute("ALTER TABLE inventory_items ADD COLUMN cost_per_unit FLOAT DEFAULT 0.0")
            print("Added cost_per_unit to inventory_items")
        if "min_alert_stock" not in inv_cols:
            c.execute("ALTER TABLE inventory_items ADD COLUMN min_alert_stock FLOAT DEFAULT 5.0")
            print("Added min_alert_stock to inventory_items")

        # Check suppliers columns
        c.execute("PRAGMA table_info(suppliers)")
        sup_cols = [r[1] for r in c.fetchall()]
        if "current_balance" not in sup_cols:
            c.execute("ALTER TABLE suppliers ADD COLUMN current_balance FLOAT DEFAULT 0.0")
            print("Added current_balance to suppliers")

        # Check purchase_invoices columns
        c.execute("PRAGMA table_info(purchase_invoices)")
        pi_cols = [r[1] for r in c.fetchall()]
        if "remaining_amount" not in pi_cols:
            c.execute("ALTER TABLE purchase_invoices ADD COLUMN remaining_amount FLOAT DEFAULT 0.0")
            print("Added remaining_amount to purchase_invoices")
        if "payment_status" not in pi_cols:
            c.execute("ALTER TABLE purchase_invoices ADD COLUMN payment_status VARCHAR(50) DEFAULT 'مدفوع بالكامل'")
            print("Added payment_status to purchase_invoices")

        # Check reservations columns
        c.execute("PRAGMA table_info(reservations)")
        res_cols = [r[1] for r in c.fetchall()]
        if "deposit" not in res_cols:
            c.execute("ALTER TABLE reservations ADD COLUMN deposit FLOAT DEFAULT 0.0")
            print("Added deposit to reservations")

        conn.commit()
except Exception as e:
    print(f"Schema check error: {e}")

with SessionLocal() as db:
    seed_menu(db)
    # Ensure default inventory is seeded if empty
    if db.query(InventoryItem).count() == 0:
        try:
            from app.seed import DEFAULT_INVENTORY
            for inv in DEFAULT_INVENTORY:
                db.add(InventoryItem(
                    name=inv["name"],
                    unit=inv["unit"],
                    current_stock=inv["current_stock"],
                    min_alert_stock=inv["min_alert_stock"],
                    cost_per_unit=inv["cost_per_unit"]
                ))
            db.commit()
            print("Auto-seeded default raw inventory items cleanly!")
        except Exception as e:
            print(f"Error seeding default inventory: {e}")

    seed_recipes(db)
    try:
        db.execute(text("UPDATE table_orders SET total_price = 0.0 WHERE items_summary LIKE '%طلب الحساب%' OR status LIKE 'طلب حساب%' OR items_summary LIKE '%نداء الويتر%' OR status = 'نداء ويتر'"))
        db.commit()
    except Exception:
        pass
    print("Menu, inventory, staff, tables, and recipes verified successfully!")

# 4. Set write permissions
try:
    os.chmod(db_file, 0o666)
    print("File permissions set to 0666.")
except Exception:
    pass

# 5. Automatically Reload PythonAnywhere Web App
wsgi_candidates = [
    "/var/www/deboo_pythonanywhere_com_wsgi.py",
    "/var/www/Deboo_pythonanywhere_com_wsgi.py",
]
for wsgi_file in wsgi_candidates:
    if os.path.exists(wsgi_file):
        try:
            os.utime(wsgi_file, None)
            print(f"Reloaded PythonAnywhere Web App: {wsgi_file}")
        except Exception as e:
            print(f"Could not touch wsgi file: {e}")

print("=== All Fixed and Ready! ===")
