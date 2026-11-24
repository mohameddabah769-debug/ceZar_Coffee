# -*- coding: utf-8 -*-
"""
ceZar Coffee - JSON Database Backup & Restore Engine
محرك النسخ الاحتياطي السحابي بصيغة JSON لكافيه سيزر
"""

import json
from datetime import datetime, date
from app.models import (
    MenuItem,
    InventoryItem,
    TableOrder,
    Expense,
    Employee,
    Shift,
    Supplier,
    CafeSetting,
    CafeTableConfig,
    VoidAuditLog
)

MODELS_MAP = [
    ('menu_items', MenuItem),
    ('inventory_items', InventoryItem),
    ('table_orders', TableOrder),
    ('expenses', Expense),
    ('employees', Employee),
    ('shifts', Shift),
    ('suppliers', Supplier),
    ('cafe_settings', CafeSetting),
    ('cafe_table_configs', CafeTableConfig),
    ('void_audit_logs', VoidAuditLog)
]


def _serialize_val(val):
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    return val


def _parse_val(col_type, val):
    if val is None:
        return None
    type_name = str(col_type).lower()
    if 'datetime' in type_name:
        try:
            return datetime.fromisoformat(val)
        except Exception:
            return None
    elif 'date' in type_name:
        try:
            return date.fromisoformat(val)
        except Exception:
            return None
    elif 'float' in type_name or 'numeric' in type_name:
        try:
            return float(val)
        except Exception:
            return 0.0
    elif 'int' in type_name:
        try:
            return int(val)
        except Exception:
            return 0
    elif 'bool' in type_name:
        return bool(val)
    return str(val)


def export_system_to_json(db) -> dict:
    """Exports all system tables into a structured dictionary."""
    counts = {}
    tables_data = {}

    for key, model_cls in MODELS_MAP:
        records = db.query(model_cls).all()
        rows = []
        for r in records:
            row_dict = {}
            for col in r.__table__.columns:
                row_dict[col.name] = _serialize_val(getattr(r, col.name))
            rows.append(row_dict)
        tables_data[key] = rows
        counts[key] = len(rows)

    return {
        "system": "ceZar Coffee POS & Management System",
        "version": "2.0",
        "format": "JSON Database Backup",
        "created_at": datetime.now().isoformat(),
        "counts": counts,
        "tables": tables_data
    }


def restore_system_from_json(db, backup_dict: dict) -> dict:
    """Restores database tables from a structured JSON backup dictionary."""
    if not isinstance(backup_dict, dict) or "tables" not in backup_dict:
        raise ValueError("صيغة ملف النسخة الاحتياطية غير صالحة")

    tables = backup_dict.get("tables", {})
    restored_counts = {}

    for key, model_cls in MODELS_MAP:
        rows = tables.get(key)
        if rows is None:
            continue

        # Clear existing records for this table safely
        db.query(model_cls).delete()

        col_types = {col.name: col.type for col in model_cls.__table__.columns}
        count = 0

        for row in rows:
            if not isinstance(row, dict):
                continue
            instance_args = {}
            for k, v in row.items():
                if k in col_types:
                    instance_args[k] = _parse_val(col_types[k], v)

            if instance_args:
                record = model_cls(**instance_args)
                db.add(record)
                count += 1

        db.flush()
        restored_counts[key] = count

    db.commit()
    return restored_counts
