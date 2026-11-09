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

    from app.database import engine, Base, SessionLocal
    from app.models import (
        MenuItem, TableOrder, ManagerAccount, Shift, Expense, Reservation,
        WaitingList, InventoryItem, PromoCode, MenuItemRecipe, Employee,
        SalaryPayment, EmployeeAttendance, CafeSetting, CafeTableConfig,
        InventoryWaste, Supplier, PurchaseInvoice, PurchaseInvoiceItem, VoidAuditLog
    )
    from app.seed import seed_menu, seed_recipes

    Base.metadata.create_all(bind=engine)
    print("Database tables created cleanly.")

    with SessionLocal() as db:
        seed_menu(db)
        seed_recipes(db)
        print("Menu, inventory, tables, and recipes seeded successfully!")

# 4. Set write permissions
try:
    os.chmod(db_file, 0o666)
    print("File permissions set to 0666.")
except Exception:
    pass

print("=== All Fixed and Ready! ===")
