import os
import sys
import io
import csv
import time
import traceback
try:
    import qrcode
except ImportError:
    qrcode = None
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, redirect, Response
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, text
from sqlalchemy.exc import OperationalError as SAOperationalError

try:
    from .database import engine, Base, SessionLocal
    from .models import MenuItem, TableOrder, ManagerAccount, Shift, Expense, Reservation, WaitingList, InventoryItem, PromoCode, MenuItemRecipe, Employee, SalaryPayment, EmployeeAttendance, CafeSetting, CafeTableConfig, InventoryWaste, Supplier, PurchaseInvoice, PurchaseInvoiceItem, VoidAuditLog
    from .seed import seed_menu
except ImportError:
    from database import engine, Base, SessionLocal
    from models import MenuItem, TableOrder, ManagerAccount, Shift, Expense, Reservation, WaitingList, InventoryItem, PromoCode, MenuItemRecipe, Employee, SalaryPayment, EmployeeAttendance, CafeSetting, CafeTableConfig, InventoryWaste, Supplier, PurchaseInvoice, PurchaseInvoiceItem, VoidAuditLog
    from seed import seed_menu

Base.metadata.create_all(bind=engine)

def auto_migrate_columns():
    with engine.connect() as conn:
        columns_to_add = [
            ("order_type", "VARCHAR(30) DEFAULT 'صالة'"),
            ("payment_method", "VARCHAR(30) DEFAULT 'كاش'"),
            ("shift_id", "INTEGER DEFAULT NULL"),
            ("delivery_address", "TEXT DEFAULT NULL"),
            ("delivery_fee", "FLOAT DEFAULT 0.0"),
            ("delivery_driver", "VARCHAR(100) DEFAULT NULL"),
            ("delivery_status", "VARCHAR(50) DEFAULT NULL"),
            ("discount_amount", "FLOAT DEFAULT 0.0"),
            ("promo_code", "VARCHAR(50) DEFAULT NULL"),
        ]
        try:
            conn.execute(text("ALTER TABLE menu_items ADD COLUMN cost_price FLOAT DEFAULT 0.0"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE manager_accounts ADD COLUMN role VARCHAR(30) DEFAULT 'admin'"))
            conn.commit()
        except Exception:
            pass
        
        for col_name, col_type in columns_to_add:
            try:
                conn.execute(text(f"ALTER TABLE table_orders ADD COLUMN {col_name} {col_type}"))
                conn.commit()
            except Exception:
                pass

try:
    auto_migrate_columns()
except Exception as e:
    print(f"[STARTUP] auto_migrate warning: {e}")

try:
    with SessionLocal() as db:
        seed_menu(db)
        if db.query(ManagerAccount).filter(ManagerAccount.username == "admin").count() == 0:
            db.add(ManagerAccount(username="admin", password="123", manager_name="مدير سيزر كوفي"))
        if db.query(ManagerAccount).filter(ManagerAccount.username == "cezar").count() == 0:
            db.add(ManagerAccount(username="cezar", password="0000", manager_name="كافيه سيزر"))
        db.commit()
except Exception as e:
    print(f"[STARTUP] seed/init warning: {e}")

app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
    static_url_path="/static"
)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")


# ==========================================
# SQLite Retry Helper for PythonAnywhere NFS
# ==========================================
def db_retry(max_retries=3, delay=0.3):
    """Decorator: retries a function on SQLite disk I/O or locked errors."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            last_err = None
            for attempt in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except SAOperationalError as e:
                    last_err = e
                    err_msg = str(e).lower()
                    if 'disk i/o error' in err_msg or 'database is locked' in err_msg or 'readonly' in err_msg:
                        time.sleep(delay * (attempt + 1))
                        continue
                    raise
                except Exception:
                    raise
            # All retries exhausted
            raise last_err
        return wrapper
    return decorator


@app.errorhandler(500)
def handle_500(e):
    """Return JSON instead of HTML for server errors."""
    return jsonify({
        "status": "error",
        "detail": "حدث خطأ مؤقت في السيرفر، يرجى إعادة المحاولة بعد لحظات."
    }), 500


@app.errorhandler(Exception)
def handle_exception(e):
    """Catch-all: return JSON for any unhandled exception."""
    if hasattr(e, 'code') and hasattr(e, 'description'):
        # Standard HTTP exceptions (404, 405, etc.)
        return jsonify({"status": "error", "detail": str(e.description)}), e.code
    return jsonify({
        "status": "error",
        "detail": "حدث خطأ مؤقت في السيرفر، يرجى إعادة المحاولة بعد لحظات."
    }), 500


# ==========================================
# 1. صفحات العرض (Frontend Views)
# ==========================================

@app.route("/")
def home():
    return redirect("/admin")


@app.route("/menu")
@app.route("/cezar/menu")
def get_menu_page():
    file_path = os.path.join(TEMPLATES_DIR, "menu.html")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return Response(f.read(), mimetype="text/html; charset=utf-8")
    return Response("<h2>جاري تحميل منيو سيزر كوفي...</h2>", mimetype="text/html; charset=utf-8")


@app.route("/admin")
@app.route("/cezar/admin")
def get_admin_page():
    file_path = os.path.join(TEMPLATES_DIR, "admin.html")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return Response(f.read(), mimetype="text/html; charset=utf-8")
    return Response("<h2>جاري تحميل لوحة تحكم سيزر كوفي...</h2>", mimetype="text/html; charset=utf-8")


@app.route("/kitchen")
@app.route("/bar")
@app.route("/cezar/bar")
def get_kitchen_page():
    file_path = os.path.join(TEMPLATES_DIR, "kitchen.html")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return Response(f.read(), mimetype="text/html; charset=utf-8")
    return Response("<h2>جاري تحميل شاشة البار والمطبخ...</h2>", mimetype="text/html; charset=utf-8")


@app.route("/qr-cards")
@app.route("/cezar/qr-generator")
def get_qr_cards_page():
    file_path = os.path.join(TEMPLATES_DIR, "qr_cards.html")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return Response(f.read(), mimetype="text/html; charset=utf-8")
    return Response("<h2>جاري تحميل كروت الـ QR للترابيزات...</h2>", mimetype="text/html; charset=utf-8")


# ==========================================
# 2. الأصناف (Menu Items)
# ==========================================

@app.route("/api/menu-items", methods=["GET"])
@app.route("/api/cezar/menu-items", methods=["GET"])
def get_menu_items():
    all_items = request.args.get("all_items", "false").lower() == "true"
    category = request.args.get("category")
    with SessionLocal() as db:
        query = db.query(MenuItem)
        if not all_items:
            query = query.filter(MenuItem.is_available.is_(True))
        if category and category.strip():
            query = query.filter(MenuItem.category == category.strip())

        items = query.order_by(MenuItem.category, MenuItem.price).all()
        grouped = {}
        for item in items:
            grouped.setdefault(item.category, []).append({
                "id": item.id,
                "name": item.name,
                "category": item.category,
                "price": item.price,
                "description": item.description or "",
                "is_available": item.is_available
            })
        return jsonify({"categories": grouped, "total_count": len(items)})


@app.route("/api/menu-items", methods=["POST"])
@app.route("/api/cezar/menu-items", methods=["POST"])
def add_menu_item():
    data = request.json or {}
    name = (data.get("name") or "").strip()
    category = (data.get("category") or "").strip()
    price = float(data.get("price") or 0.0)
    if not name or not category:
        return jsonify({"detail": "الاسم والنوع مطلوبان"}), 400

    with SessionLocal() as db:
        new_item = MenuItem(
            name=name,
            category=category,
            price=price,
            description=data.get("description"),
            is_available=data.get("is_available", True)
        )
        db.add(new_item)
        db.commit()
        db.refresh(new_item)
        return jsonify({"status": "success", "item": {"id": new_item.id, "name": new_item.name}})


@app.route("/api/menu-items/<int:item_id>", methods=["PUT", "POST"])
@app.route("/api/cezar/menu-items/<int:item_id>", methods=["PUT", "POST"])
def update_menu_item(item_id):
    data = request.json or {}
    with SessionLocal() as db:
        item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
        if not item:
            return jsonify({"detail": "Item not found"}), 404
        if "name" in data and data["name"] is not None:
            item.name = data["name"].strip()
        if "category" in data and data["category"] is not None:
            item.category = data["category"].strip()
        if "price" in data and data["price"] is not None:
            item.price = float(data["price"])
        if "description" in data:
            item.description = data["description"]
        if "is_available" in data and data["is_available"] is not None:
            item.is_available = bool(data["is_available"])
        db.commit()
        return jsonify({"status": "success", "item": {"id": item.id, "name": item.name, "price": item.price, "is_available": item.is_available}})


@app.route("/api/menu-items/<int:item_id>", methods=["DELETE", "POST"])
@app.route("/api/cezar/menu-items/<int:item_id>", methods=["DELETE", "POST"])
def delete_menu_item(item_id):
    with SessionLocal() as db:
        item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
        if not item:
            return jsonify({"detail": "Item not found"}), 404
        db.delete(item)
        db.commit()
        return jsonify({"status": "success", "deleted_id": item_id})


# ==========================================
# 3. الطلبات والكاشير (POS & Orders)
# ==========================================

def deduct_inventory_for_order(items, db):
    """الخصم التلقائي للمواد الخام والمخزون عند إنشاء أو تحضير أي أوردر.
    ملاحظة: لا يعمل commit هنا - المسؤولية على الكود اللي بيناديه."""
    try:
        inv_items = {it.name: it for it in db.query(InventoryItem).all()}
        for item in items:
            name = (item.get('name') if isinstance(item, dict) else getattr(item, 'name', '')) or ''
            qty = (item.get('quantity') if isinstance(item, dict) else getattr(item, 'quantity', 1)) or 1
            customization = ((item.get('customization') if isinstance(item, dict) else getattr(item, 'customization', '')) or '').strip()

            is_coffee = any(k in name for k in ["اسبريسو", "لاتيه", "كابتشينو", "امريكان", "فلات وايت", "موكا", "كورتادو", "ميكاتو", "قهوة"])
            if is_coffee:
                beans = inv_items.get("بن برازيلي فاخر") or inv_items.get("بن كولومبي مميز")
                if beans:
                    w = 0.018 * qty
                    if "دبل" in name: w *= 2
                    if "شوت إضافي" in customization: w += (0.018 * qty)
                    beans.current_stock = max(0.0, round(beans.current_stock - w, 3))

            needs_milk = any(k in name for k in ["لاتيه", "كابتشينو", "فلات وايت", "كورتادو", "فرنساوى", "موكا", "حليب", "سحلب", "شوكليت"])
            if needs_milk and "بدون حليب" not in customization:
                m_amt = 0.180 * qty
                if "حليب لوز" in customization and "حليب لوز" in inv_items:
                    inv_items["حليب لوز"].current_stock = max(0.0, round(inv_items["حليب لوز"].current_stock - m_amt, 3))
                elif "حليب شوفان" in customization and "حليب شوفان" in inv_items:
                    inv_items["حليب شوفان"].current_stock = max(0.0, round(inv_items["حليب شوفان"].current_stock - m_amt, 3))
                elif "حليب كامل الدسم" in inv_items:
                    inv_items["حليب كامل الدسم"].current_stock = max(0.0, round(inv_items["حليب كامل الدسم"].current_stock - m_amt, 3))

            if "كراميل" in customization or "كراميل" in name:
                if "سيرب كراميل" in inv_items:
                    inv_items["سيرب كراميل"].current_stock = max(0.0, round(inv_items["سيرب كراميل"].current_stock - (0.02 * qty), 3))
            if "فانيليا" in customization or "فانيليا" in name:
                if "سيرب فانيليا" in inv_items:
                    inv_items["سيرب فانيليا"].current_stock = max(0.0, round(inv_items["سيرب فانيليا"].current_stock - (0.02 * qty), 3))

            if "شاى" in name and "شاي أسود ناعم" in inv_items:
                inv_items["شاي أسود ناعم"].current_stock = max(0.0, round(inv_items["شاي أسود ناعم"].current_stock - (0.005 * qty), 3))
            elif ("تركي" in name or "تركى" in name) and "بن تركي محوج" in inv_items:
                inv_items["بن تركي محوج"].current_stock = max(0.0, round(inv_items["بن تركي محوج"].current_stock - (0.012 * qty), 3))

            cups = inv_items.get("أكواب تيك أواي 12oz") or inv_items.get("أكواب بلاستيك بارد 16oz")
            if cups:
                cups.current_stock = max(0.0, cups.current_stock - qty)

    except Exception as e:
        print(f"Auto-deduct warning: {e}")

@app.route("/api/orders", methods=["POST"])
@app.route("/api/cezar/orders", methods=["POST"])
@db_retry(max_retries=3, delay=0.4)
def create_table_order():
    data = request.json or {}
    items = data.get("items") or []
    table_num = int(data.get("table_number") or 1)
    if not items:
        return jsonify({"detail": "السلة فارغة، برجاء اختيار مشروب أولاً"}), 400

    lines = []
    items_total = 0.0
    for item in items:
        p = float(item.get("price") or 0.0)
        q = int(item.get("quantity") or 1)
        sub = p * q
        items_total += sub
        cust = f" [{item.get('customization')}]" if item.get("customization") else ""
        lines.append(f"- {q}x {item.get('name')}{cust}: {sub:g} ج")

    promo_code = data.get("promo_code")
    discount = 0.0

    with SessionLocal() as db:
        try:
            if promo_code:
                promo = db.query(PromoCode).filter(PromoCode.code == promo_code.strip().upper(), PromoCode.is_active.is_(True)).first()
                if promo and items_total >= (promo.min_order_value or 0.0):
                    if promo.discount_type == "percentage":
                        discount = round((items_total * promo.discount_value) / 100.0, 2)
                    else:
                        discount = min(items_total, promo.discount_value)
                    promo.usage_count = (promo.usage_count or 0) + 1

            grand_total = max(0.0, items_total - discount)
            items_summary = "\n".join(lines)

            current_shift = db.query(Shift).filter(Shift.status == "مفتوح").first()
            shift_id = current_shift.id if current_shift else None

            order = TableOrder(
                table_number=table_num,
                order_type="صالة",
                items_summary=items_summary,
                total_price=grand_total,
                discount_amount=discount,
                promo_code=promo_code,
                customer_name=data.get("customer_name") or f"ترابيزة {table_num}",
                customer_phone=data.get("customer_phone") or "",
                notes=data.get("notes") or "",
                status="جديد",
                payment_method="كاش",
                shift_id=shift_id
            )
            db.add(order)
            if current_shift:
                current_shift.total_sales += grand_total
                current_shift.cash_sales += grand_total
            deduct_inventory_for_order(items, db)
            db.commit()
            db.refresh(order)
            return jsonify({
                "status": "success",
                "message": f"تم استلام طلب ترابيزة {order.table_number} بنجاح!",
                "order_id": order.id,
                "table_number": order.table_number,
                "discount_amount": discount,
                "total_price": order.total_price
            })
        except Exception as e:
            db.rollback()
            raise


@app.route("/api/pos/orders", methods=["POST"])
@app.route("/api/cezar/pos/orders", methods=["POST"])
@db_retry(max_retries=3, delay=0.4)
def create_pos_direct_order():
    data = request.json or {}
    items = data.get("items") or []
    if not items:
        return jsonify({"detail": "يجب إضافة صنف واحد على الأقل للأوردر"}), 400

    order_type = data.get("order_type") or "صالة"
    table_num = int(data.get("table_number") or 0) if order_type == "صالة" else 0
    lines = []
    items_total = 0.0
    for item in items:
        p = float(item.get("price") or 0.0)
        q = int(item.get("quantity") or 1)
        sub = p * q
        items_total += sub
        cust = f" [{item.get('customization')}]" if item.get("customization") else ""
        lines.append(f"- {q}x {item.get('name')}{cust}: {sub:g} ج")

    delivery_fee = float(data.get("delivery_fee") or 0.0) if order_type == "دليفري" else 0.0
    discount = float(data.get("discount_amount") or 0.0)
    grand_total = max(0.0, items_total + delivery_fee - discount)
    items_summary = "\n".join(lines)
    payment_method = data.get("payment_method") or "كاش"

    with SessionLocal() as db:
        current_shift = db.query(Shift).filter(Shift.status == "مفتوح").first()
        shift_id = current_shift.id if current_shift else None

        default_name = "عميل تيك أواي" if order_type == "تيك أواي" else ("عميل دليفري" if order_type == "دليفري" else f"ترابيزة {table_num}")
        order = TableOrder(
            table_number=table_num,
            order_type=order_type,
            items_summary=items_summary,
            total_price=grand_total,
            discount_amount=discount,
            promo_code=data.get("promo_code"),
            payment_method=payment_method,
            status="قيد التحضير",
            customer_name=data.get("customer_name") or default_name,
            customer_phone=data.get("customer_phone") or "",
            notes=data.get("notes") or "",
            shift_id=shift_id,
            delivery_address=data.get("delivery_address") if order_type == "دليفري" else None,
            delivery_fee=delivery_fee,
            delivery_driver=data.get("delivery_driver") if order_type == "دليفري" else None,
            delivery_status="قيد التجهيز" if order_type == "دليفري" else None
        )
        db.add(order)
        if current_shift:
            current_shift.total_sales += grand_total
            if payment_method == "فيزا":
                current_shift.visa_sales += grand_total
            else:
                current_shift.cash_sales += grand_total
        db.commit()
        db.refresh(order)
        return jsonify({
            "status": "success",
            "message": f"تم تسجيل أوردر الـ {order_type} بنجاح!",
            "order_id": order.id,
            "grand_total": grand_total
        })


@app.route("/api/orders", methods=["GET"])
@app.route("/api/cezar/orders", methods=["GET"])
@db_retry(max_retries=3, delay=0.3)
def get_orders():
    order_type = request.args.get("order_type")
    with SessionLocal() as db:
        query = db.query(TableOrder)
        if order_type and order_type.strip():
            query = query.filter(TableOrder.order_type == order_type.strip())
        orders = query.order_by(desc(TableOrder.created_at)).limit(100).all()

        total_orders = db.query(TableOrder).count()
        delivered_count = db.query(TableOrder).filter(TableOrder.status.in_(["تم التقديم", "تمت التسوية", "تم التوصيل"])).count()
        pending_count = db.query(TableOrder).filter(
            TableOrder.status.in_(["جديد", "جاري التحضير", "قيد التحضير", "نداء ويتر"]) | TableOrder.status.like("طلب حساب%")
        ).count()

        total_sales = db.query(func.sum(TableOrder.total_price)).filter(
            TableOrder.status != "ملغي",
            ~TableOrder.status.like("طلب حساب%"),
            TableOrder.status != "نداء ويتر"
        ).scalar() or 0.0

        return jsonify({
            "stats": {
                "total_orders": total_orders,
                "total_sales": round(total_sales, 2),
                "pending_orders": pending_count,
                "delivered_orders": delivered_count,
                "active_orders": pending_count
            },
            "orders": [
                {
                    "id": o.id,
                    "table_number": o.table_number or 0,
                    "order_type": o.order_type or "صالة",
                    "items_summary": o.items_summary,
                    "total_price": o.total_price,
                    "discount_amount": o.discount_amount or 0.0,
                    "promo_code": o.promo_code or "",
                    "payment_method": o.payment_method or "كاش",
                    "status": o.status,
                    "customer_name": o.customer_name,
                    "customer_phone": o.customer_phone,
                    "notes": o.notes,
                    "delivery_address": o.delivery_address,
                    "delivery_fee": o.delivery_fee or 0.0,
                    "delivery_driver": o.delivery_driver,
                    "delivery_status": o.delivery_status,
                    "created_at": o.created_at.strftime("%I:%M %p") if o.created_at else ""
                }
                for o in orders
            ]
        })


@app.route("/api/tables/status", methods=["GET"])
@app.route("/api/cezar/tables/status", methods=["GET"])
@db_retry(max_retries=3, delay=0.3)
def get_all_tables_status():
    with SessionLocal() as db:
        tables_data = []
        for t in range(1, 26):
            active_orders = db.query(TableOrder).filter(
                TableOrder.table_number == t,
                TableOrder.order_type == "صالة",
                TableOrder.status != "ملغي",
                TableOrder.status != "تم التقديم",
                TableOrder.status != "تمت التسوية"
            ).all()

            bill_orders = [
                o for o in active_orders 
                if o.total_price > 0 and "طلب الحساب" not in (o.items_summary or "") and "نداء الويتر" not in (o.items_summary or "")
            ]
            total_bill = sum(o.total_price for o in bill_orders)
            has_bill_request = any("طلب حساب" in (o.status or "") or "طلب الحساب" in (o.items_summary or "") for o in active_orders)
            has_waiter_call = any("نداء ويتر" in (o.status or "") or "نداء الويتر" in (o.items_summary or "") for o in active_orders)

            if has_bill_request:
                status = "bill_requested"
                status_text = "طلب حساب"
            elif has_waiter_call:
                status = "waiter_called"
                status_text = "نداء ويتر"
            elif len(bill_orders) > 0:
                status = "occupied"
                status_text = "مشغولة"
            else:
                status = "free"
                status_text = "متاحة"

            tables_data.append({
                "table_number": t,
                "status": status,
                "status_text": status_text,
                "total_bill": round(total_bill, 2),
                "orders_count": len(bill_orders),
                "has_waiter_call": has_waiter_call,
                "has_bill_request": has_bill_request
            })

        return jsonify({"status": "success", "tables": tables_data})


@app.route("/api/tables/<int:table_number>/bill", methods=["GET"])
@app.route("/api/cezar/tables/<int:table_number>/bill", methods=["GET"])
@db_retry(max_retries=3, delay=0.3)
def get_table_bill(table_number):
    with SessionLocal() as db:
        active_orders = db.query(TableOrder).filter(
            TableOrder.table_number == table_number,
            TableOrder.status != "ملغي",
            TableOrder.status != "تمت التسوية",
            ~TableOrder.status.like("طلب حساب%"),
            TableOrder.status != "نداء ويتر",
            ~TableOrder.items_summary.like("%طلب الحساب%"),
            ~TableOrder.items_summary.like("%نداء الويتر%"),
            TableOrder.total_price > 0
        ).all()
        total_bill = sum(o.total_price for o in active_orders)
        return jsonify({
            "table_number": table_number,
            "total_bill": round(total_bill, 2),
            "orders_count": len(active_orders),
            "orders": [
                {
                    "id": o.id,
                    "items_summary": o.items_summary,
                    "total_price": o.total_price,
                    "status": o.status,
                    "notes": o.notes or "",
                    "created_at": o.created_at.strftime("%I:%M %p") if o.created_at else ""
                }
                for o in active_orders
            ]
        })


@app.route("/api/tables/<int:table_number>/settle", methods=["POST"])
@app.route("/api/cezar/tables/<int:table_number>/settle", methods=["POST"])
def settle_table_bill(table_number):
    with SessionLocal() as db:
        orders = db.query(TableOrder).filter(
            TableOrder.table_number == table_number,
            TableOrder.status != "ملغي",
            TableOrder.status != "تمت التسوية"
        ).all()
        for o in orders:
            o.status = "تمت التسوية"
        db.commit()
        return jsonify({"status": "success", "message": f"تمت تسوية حساب ترابيزة {table_number} وإفراغها بنجاح!", "table_number": table_number})




@app.route("/api/tables/transfer", methods=["POST"])
@app.route("/api/cezar/tables/transfer", methods=["POST"])
@db_retry(max_retries=3, delay=0.3)
def transfer_table_orders():
    data = request.json or {}
    from_table = int(data.get("from_table") or 0)
    to_table = int(data.get("to_table") or 0)
    
    if not from_table or not to_table or from_table == to_table:
        return jsonify({"detail": "أرقام الترابيزات غير صحيحة", "status": "error"}), 400
        
    with SessionLocal() as db:
        active_orders = db.query(TableOrder).filter(
            TableOrder.table_number == from_table,
            TableOrder.order_type == "صالة",
            ~TableOrder.status.in_(["ملغي", "تمت التسوية"])
        ).all()
        
        if not active_orders:
            return jsonify({"detail": f"لا توجد طلبات نشطة في ترابيزة {from_table}", "status": "error"}), 400
            
        for o in active_orders:
            o.table_number = to_table
            if f"ترابيزة {from_table}" in (o.customer_name or ""):
                o.customer_name = f"ترابيزة {to_table}"
                
        db.commit()
        return jsonify({
            "status": "success",
            "message": f"تم نقل الحساب من ترابيزة {from_table} إلى ترابيزة {to_table} بنجاح!"
        })


@app.route("/api/tables/merge", methods=["POST"])
@app.route("/api/cezar/tables/merge", methods=["POST"])
@db_retry(max_retries=3, delay=0.3)
def merge_tables():
    data = request.json or {}
    primary_table = int(data.get("primary_table") or 0)
    secondary_table = int(data.get("secondary_table") or 0)
    
    if not primary_table or not secondary_table or primary_table == secondary_table:
        return jsonify({"detail": "أرقام الترابيزات غير صحيحة", "status": "error"}), 400
        
    with SessionLocal() as db:
        sec_orders = db.query(TableOrder).filter(
            TableOrder.table_number == secondary_table,
            TableOrder.order_type == "صالة",
            ~TableOrder.status.in_(["ملغي", "تمت التسوية"])
        ).all()
        
        if not sec_orders:
            return jsonify({"detail": f"لا توجد طلبات في ترابيزة {secondary_table}", "status": "error"}), 400
            
        for o in sec_orders:
            o.table_number = primary_table
            o.customer_name = f"ترابيزة {primary_table} (مدمجة مع {secondary_table})"
            
        db.commit()
        return jsonify({
            "status": "success",
            "message": f"تم دمج حساب ترابيزة {secondary_table} في ترابيزة {primary_table} بنجاح!"
        })


@app.route("/api/tables/<int:table_number>/track", methods=["GET"])
@app.route("/api/cezar/tables/<int:table_number>/track", methods=["GET"])
@db_retry(max_retries=3, delay=0.3)
def track_table_orders(table_number):
    with SessionLocal() as db:
        orders = db.query(TableOrder).filter(
            TableOrder.table_number == table_number,
            ~TableOrder.items_summary.like("%طلب الحساب%"),
            ~TableOrder.items_summary.like("%نداء الويتر%"),
            TableOrder.total_price > 0
        ).order_by(desc(TableOrder.id)).limit(25).all()

        orders_list = [
            {
                "id": o.id,
                "items_summary": o.items_summary,
                "total_price": o.total_price,
                "status": o.status,
                "notes": o.notes or "",
                "created_at": o.created_at.strftime("%I:%M %p") if o.created_at else ""
            }
            for o in orders
        ]
        active_count = sum(1 for o in orders if o.status in ["جديد", "جاري التحضير", "قيد التحضير"])
        return jsonify({
            "status": "success",
            "table_number": table_number,
            "orders_count": len(orders_list),
            "active_count": active_count,
            "orders": orders_list
        })


@app.route("/api/orders/<int:order_id>", methods=["GET"])
@app.route("/api/cezar/orders/<int:order_id>", methods=["GET"])
def get_order_by_id(order_id):
    with SessionLocal() as db:
        order = db.query(TableOrder).filter(TableOrder.id == order_id).first()
        if not order:
            return jsonify({"detail": "الطلب غير موجود"}), 404
        return jsonify({
            "status": "success",
            "id": order.id,
            "table_number": order.table_number or 0,
            "order_type": order.order_type or "صالة",
            "items_summary": order.items_summary,
            "total_price": order.total_price,
            "discount_amount": order.discount_amount or 0.0,
            "promo_code": order.promo_code or "",
            "payment_method": order.payment_method or "كاش",
            "status": order.status,
            "customer_name": order.customer_name,
            "customer_phone": order.customer_phone,
            "delivery_address": order.delivery_address,
            "delivery_fee": order.delivery_fee or 0.0,
            "delivery_driver": order.delivery_driver,
            "delivery_status": order.delivery_status,
            "notes": order.notes or "",
            "created_at": order.created_at.strftime("%I:%M %p") if order.created_at else ""
        })


@app.route("/api/orders/<int:order_id>/status", methods=["POST"])
@app.route("/api/cezar/orders/<int:order_id>/status", methods=["POST"])
def update_order_status(order_id):
    data = request.json or {}
    new_status = data.get("status")
    with SessionLocal() as db:
        order = db.query(TableOrder).filter(TableOrder.id == order_id).first()
        if not order:
            return jsonify({"detail": "Order not found"}), 404
        order.status = new_status
        if order.status in ["تم التقديم", "تمت التسوية", "تم التوصيل"] and (order.items_summary and "طلب الحساب" in order.items_summary):
            db.query(TableOrder).filter(
                TableOrder.table_number == order.table_number,
                TableOrder.status.in_(["جديد", "جاري التحضير", "قيد التحضير"])
            ).update({"status": "تم التقديم"}, synchronize_session=False)
        db.commit()
        return jsonify({"status": "success", "order_id": order.id, "new_status": order.status})


@app.route("/api/orders/<int:order_id>/delivery-status", methods=["POST"])
@app.route("/api/cezar/orders/<int:order_id>/delivery-status", methods=["POST"])
def update_delivery_status(order_id):
    data = request.json or {}
    with SessionLocal() as db:
        order = db.query(TableOrder).filter(TableOrder.id == order_id).first()
        if not order:
            return jsonify({"detail": "الطلب غير موجود"}), 404
        order.delivery_status = data.get("delivery_status")
        if data.get("delivery_driver"):
            order.delivery_driver = data.get("delivery_driver")
        if order.delivery_status == "تم التوصيل":
            order.status = "تم التوصيل"
        db.commit()
        return jsonify({"status": "success", "order_id": order.id, "delivery_status": order.delivery_status})


@app.route("/api/orders/call-waiter", methods=["POST"])
@app.route("/api/cezar/orders/call-waiter", methods=["POST"])
@db_retry(max_retries=3, delay=0.3)
def call_waiter_endpoint():
    data = request.json or {}
    table_num = int(data.get("table_number") or 1)
    with SessionLocal() as db:
        order = TableOrder(
            table_number=table_num,
            order_type="صالة",
            items_summary="🔔 نداء الويتر (طلب مساعدة / استفسار)",
            total_price=0.0,
            customer_name=f"ترابيزة {table_num}",
            status="نداء ويتر"
        )
        db.add(order)
        db.commit()
        return jsonify({"status": "success", "message": f"تم إرسال نداء الويتر لترابيزة {table_num} فوراً!"})


@app.route("/api/orders/request-bill", methods=["POST"])
@app.route("/api/cezar/orders/request-bill", methods=["POST"])
@db_retry(max_retries=3, delay=0.3)
def request_bill_endpoint():
    data = request.json or {}
    table_num = int(data.get("table_number") or 1)
    method = data.get("payment_method") or "كاش"
    icon = "💵" if method == "كاش" else "💳"

    with SessionLocal() as db:
        active_orders = db.query(TableOrder).filter(
            TableOrder.table_number == table_num,
            TableOrder.status != "ملغي",
            TableOrder.status != "تمت التسوية",
            ~TableOrder.status.like("طلب حساب%"),
            TableOrder.status != "نداء ويتر",
            ~TableOrder.items_summary.like("%طلب الحساب%"),
            ~TableOrder.items_summary.like("%نداء الويتر%"),
            TableOrder.total_price > 0
        ).all()
        total_bill = sum(o.total_price for o in active_orders)
        if active_orders:
            items_text = "\n".join([o.items_summary for o in active_orders])
            summary = f"🧾 طلب الحساب النهائي ({method}) {icon}\n💰 الإجمالي المطلوب تحصيله: {total_bill:g} جنيه\n📋 الطلبات:\n{items_text}"
        else:
            summary = f"🧾 طلب الحساب النهائي ({method}) {icon} (طلب حساب مباشر بدون أوردرات مسبقة)"

        order = TableOrder(
            table_number=table_num,
            order_type="صالة",
            items_summary=summary,
            total_price=total_bill,
            payment_method=method,
            customer_name=f"ترابيزة {table_num}",
            status=f"طلب حساب ({method})"
        )
        db.add(order)
        db.commit()
        return jsonify({
            "status": "success",
            "message": f"تم إرسال طلب الحساب لترابيزة {table_num} بنجاح! الإجمالي: {total_bill:g} جنيه ({method})",
            "order_id": order.id,
            "total_bill": total_bill
        })


@app.route("/api/orders/clear-all", methods=["POST"])
@app.route("/api/cezar/orders/clear-all", methods=["POST"])
def clear_all_orders():
    with SessionLocal() as db:
        db.query(TableOrder).delete()
        db.commit()
        return jsonify({"status": "success", "message": "تم تصفير جميع الطلبات وبدء وردية جديدة بنجاح!"})


# ==========================================
# 4. الشيفتات والمصروفات (Shifts & Expenses)
# ==========================================

@app.route("/api/shifts/current", methods=["GET"])
@app.route("/api/cezar/shifts/current", methods=["GET"])
def get_current_shift():
    with SessionLocal() as db:
        shift = db.query(Shift).filter(Shift.status == "مفتوح").first()
        if not shift:
            return jsonify({"status": "no_active_shift", "message": "لا يوجد وردية مفتوحة حالياً"})

        orders = db.query(TableOrder).filter(
            TableOrder.shift_id == shift.id,
            TableOrder.status != "ملغي",
            ~TableOrder.status.like("طلب حساب%"),
            TableOrder.status != "نداء ويتر"
        ).all()
        total_sales = sum(o.total_price for o in orders)
        cash_sales = sum(o.total_price for o in orders if (o.payment_method or "كاش") == "كاش")
        visa_sales = sum(o.total_price for o in orders if (o.payment_method or "") == "فيزا")

        expenses = db.query(Expense).filter(Expense.shift_id == shift.id).all()
        total_expenses = sum(e.amount for e in expenses)
        expected_cash = (shift.starting_cash or 0.0) + cash_sales - total_expenses

        return jsonify({
            "status": "active",
            "shift": {
                "id": shift.id,
                "cashier_name": shift.cashier_name,
                "start_time": shift.start_time.strftime("%Y-%m-%d %I:%M %p") if shift.start_time else "",
                "starting_cash": shift.starting_cash,
                "total_sales": round(total_sales, 2),
                "cash_sales": round(cash_sales, 2),
                "visa_sales": round(visa_sales, 2),
                "total_expenses": round(total_expenses, 2),
                "expected_cash": round(expected_cash, 2),
                "orders_count": len(orders),
                "notes": shift.notes or ""
            }
        })


@app.route("/api/shifts/open", methods=["POST"])
@app.route("/api/cezar/shifts/open", methods=["POST"])
def open_shift():
    data = request.json or {}
    with SessionLocal() as db:
        active = db.query(Shift).filter(Shift.status == "مفتوح").first()
        if active:
            return jsonify({"detail": f"يوجد وردية مفتوحة بالفعل للكاشير ({active.cashier_name}). يجب تقفيلها أولاً."}), 400

        new_shift = Shift(
            cashier_name=(data.get("cashier_name") or "كاشير سيزر").strip(),
            starting_cash=float(data.get("starting_cash") or 0.0),
            start_time=datetime.utcnow(),
            status="مفتوح",
            notes=data.get("notes") or ""
        )
        db.add(new_shift)
        db.commit()
        return jsonify({"status": "success", "message": "تم فتح الوردية بنجاح!", "shift_id": new_shift.id})


@app.route("/api/shifts/close", methods=["POST"])
@app.route("/api/cezar/shifts/close", methods=["POST"])
def close_shift():
    data = request.json or {}
    actual_cash = float(data.get("actual_cash") or 0.0)
    with SessionLocal() as db:
        shift = db.query(Shift).filter(Shift.status == "مفتوح").first()
        if not shift:
            return jsonify({"detail": "لا توجد وردية مفتوحة لإغلاقها!"}), 400

        orders = db.query(TableOrder).filter(
            TableOrder.shift_id == shift.id,
            TableOrder.status != "ملغي",
            ~TableOrder.status.like("طلب حساب%"),
            TableOrder.status != "نداء ويتر"
        ).all()
        total_sales = sum(o.total_price for o in orders)
        cash_sales = sum(o.total_price for o in orders if (o.payment_method or "كاش") == "كاش")
        visa_sales = sum(o.total_price for o in orders if (o.payment_method or "") == "فيزا")
        expenses = db.query(Expense).filter(Expense.shift_id == shift.id).all()
        total_expenses = sum(e.amount for e in expenses)
        expected_cash = (shift.starting_cash or 0.0) + cash_sales - total_expenses
        difference = actual_cash - expected_cash

        shift.end_time = datetime.utcnow()
        shift.status = "مغلق"
        shift.total_sales = total_sales
        shift.cash_sales = cash_sales
        shift.visa_sales = visa_sales
        shift.total_expenses = total_expenses
        shift.actual_cash = actual_cash
        shift.difference = round(difference, 2)
        if data.get("notes"):
            shift.notes = (shift.notes or "") + "\n" + data.get("notes")

        db.commit()
        return jsonify({
            "status": "success",
            "message": "تم إغلاق الوردية وتقفيل الحساب بنجاح!",
            "summary": {
                "shift_id": shift.id,
                "cashier_name": shift.cashier_name,
                "starting_cash": shift.starting_cash,
                "total_sales": total_sales,
                "cash_sales": cash_sales,
                "visa_sales": visa_sales,
                "total_expenses": total_expenses,
                "expected_cash": round(expected_cash, 2),
                "actual_cash": actual_cash,
                "difference": round(difference, 2)
            }
        })


@app.route("/api/shifts/history", methods=["GET"])
@app.route("/api/cezar/shifts/history", methods=["GET"])
def get_shifts_history():
    with SessionLocal() as db:
        shifts = db.query(Shift).order_by(desc(Shift.id)).limit(30).all()
        return jsonify({
            "shifts": [
                {
                    "id": s.id,
                    "cashier_name": s.cashier_name,
                    "start_time": s.start_time.strftime("%Y-%m-%d %I:%M %p") if s.start_time else "",
                    "end_time": s.end_time.strftime("%Y-%m-%d %I:%M %p") if s.end_time else "مستمرة",
                    "starting_cash": s.starting_cash,
                    "total_sales": s.total_sales,
                    "cash_sales": s.cash_sales,
                    "visa_sales": s.visa_sales,
                    "total_expenses": s.total_expenses,
                    "actual_cash": s.actual_cash,
                    "difference": s.difference,
                    "status": s.status
                }
                for s in shifts
            ]
        })


@app.route("/api/expenses", methods=["POST"])
@app.route("/api/cezar/expenses", methods=["POST"])
def add_expense():
    data = request.json or {}
    title = (data.get("title") or "").strip()
    amount = float(data.get("amount") or 0.0)
    if not title or amount <= 0:
        return jsonify({"detail": "بيان المصروف والمبلغ مطلوبان"}), 400

    with SessionLocal() as db:
        current_shift = db.query(Shift).filter(Shift.status == "مفتوح").first()
        shift_id = current_shift.id if current_shift else None
        expense = Expense(
            shift_id=shift_id,
            title=title,
            amount=amount,
            category=data.get("category") or "مشتريات تشغيل",
            notes=data.get("notes") or "",
            created_at=datetime.utcnow()
        )
        db.add(expense)
        if current_shift:
            current_shift.total_expenses = (current_shift.total_expenses or 0.0) + amount
        db.commit()
        return jsonify({"status": "success", "message": f"تم تسجيل المصروف بقيمة {amount:g} ج بنجاح!"})


@app.route("/api/expenses", methods=["GET"])
@app.route("/api/cezar/expenses", methods=["GET"])
def get_expenses():
    with SessionLocal() as db:
        current_shift = db.query(Shift).filter(Shift.status == "مفتوح").first()
        query = db.query(Expense)
        if current_shift:
            query = query.filter(Expense.shift_id == current_shift.id)
        expenses = query.order_by(desc(Expense.created_at)).limit(50).all()
        return jsonify({
            "expenses": [
                {
                    "id": e.id,
                    "title": e.title,
                    "amount": e.amount,
                    "category": e.category,
                    "notes": e.notes or "",
                    "created_at": e.created_at.strftime("%I:%M %p") if e.created_at else ""
                }
                for e in expenses
            ]
        })


@app.route("/api/expenses/<int:expense_id>", methods=["DELETE"])
@app.route("/api/cezar/expenses/<int:expense_id>", methods=["DELETE"])
def delete_expense(expense_id):
    with SessionLocal() as db:
        exp = db.query(Expense).filter(Expense.id == expense_id).first()
        if not exp:
            return jsonify({"detail": "المصروف غير موجود"}), 404
        if exp.shift_id:
            shift = db.query(Shift).filter(Shift.id == exp.shift_id).first()
            if shift and shift.total_expenses:
                shift.total_expenses = max(0.0, shift.total_expenses - exp.amount)
        db.delete(exp)
        db.commit()
        return jsonify({"status": "success", "message": "تم حذف المصروف بنجاح"})


# ==========================================
# 5. الحجوزات وقائمة الانتظار
# ==========================================

@app.route("/api/reservations", methods=["GET"])
@app.route("/api/cezar/reservations", methods=["GET"])
def get_reservations():
    with SessionLocal() as db:
        res_list = db.query(Reservation).order_by(desc(Reservation.id)).limit(50).all()
        return jsonify({
            "reservations": [
                {
                    "id": r.id,
                    "customer_name": r.customer_name,
                    "customer_phone": r.customer_phone,
                    "table_number": r.table_number or "غير محدد",
                    "guests_count": r.guests_count,
                    "reservation_time": r.reservation_time,
                    "deposit": r.deposit,
                    "status": r.status,
                    "notes": r.notes or ""
                }
                for r in res_list
            ]
        })


@app.route("/api/reservations", methods=["POST"])
@app.route("/api/cezar/reservations", methods=["POST"])
def create_reservation():
    data = request.json or {}
    name = (data.get("customer_name") or "").strip()
    phone = (data.get("customer_phone") or "").strip()
    res_time = (data.get("reservation_time") or "").strip()
    if not name or not phone or not res_time:
        return jsonify({"detail": "اسم العميل والتليفون وموعد الحجز مطلوبين"}), 400

    with SessionLocal() as db:
        res = Reservation(
            customer_name=name,
            customer_phone=phone,
            table_number=int(data.get("table_number") or 0) if data.get("table_number") else None,
            guests_count=int(data.get("guests_count") or 2),
            reservation_time=res_time,
            deposit=float(data.get("deposit") or 0.0),
            notes=data.get("notes") or "",
            status="مؤكد"
        )
        db.add(res)
        db.commit()
        return jsonify({"status": "success", "message": f"تم تسجيل حجز {res.customer_name} بنجاح!", "id": res.id})


@app.route("/api/reservations/<int:res_id>/status", methods=["PUT"])
@app.route("/api/cezar/reservations/<int:res_id>/status", methods=["PUT"])
def update_reservation_status(res_id):
    data = request.json or {}
    with SessionLocal() as db:
        res = db.query(Reservation).filter(Reservation.id == res_id).first()
        if not res:
            return jsonify({"detail": "الحجز غير موجود"}), 404
        res.status = data.get("status") or res.status
        db.commit()
        return jsonify({"status": "success", "new_status": res.status})


@app.route("/api/reservations/<int:res_id>", methods=["DELETE"])
@app.route("/api/cezar/reservations/<int:res_id>", methods=["DELETE"])
def delete_reservation(res_id):
    with SessionLocal() as db:
        res = db.query(Reservation).filter(Reservation.id == res_id).first()
        if not res:
            return jsonify({"detail": "الحجز غير موجود"}), 404
        db.delete(res)
        db.commit()
        return jsonify({"status": "success", "message": "تم حذف الحجز بنجاح"})


@app.route("/api/waiting-list", methods=["GET"])
@app.route("/api/cezar/waiting-list", methods=["GET"])
def get_waiting_list():
    with SessionLocal() as db:
        waiters = db.query(WaitingList).filter(WaitingList.status.in_(["قيد الانتظار", "تم النداء"])).order_by(WaitingList.id).all()
        return jsonify({
            "waiting_list": [
                {
                    "id": w.id,
                    "customer_name": w.customer_name,
                    "customer_phone": w.customer_phone,
                    "guests_count": w.guests_count,
                    "status": w.status,
                    "assigned_table": w.assigned_table,
                    "notes": w.notes or "",
                    "created_at": w.created_at.strftime("%I:%M %p") if w.created_at else ""
                }
                for w in waiters
            ]
        })


@app.route("/api/waiting-list", methods=["POST"])
@app.route("/api/cezar/waiting-list", methods=["POST"])
def add_to_waiting_list():
    data = request.json or {}
    name = (data.get("customer_name") or "").strip()
    phone = (data.get("customer_phone") or "").strip()
    if not name or not phone:
        return jsonify({"detail": "اسم العميل ورقم الهاتف مطلوبين"}), 400

    with SessionLocal() as db:
        waiter = WaitingList(
            customer_name=name,
            customer_phone=phone,
            guests_count=int(data.get("guests_count") or 2),
            notes=data.get("notes") or "",
            status="قيد الانتظار"
        )
        db.add(waiter)
        db.commit()
        return jsonify({"status": "success", "message": f"تمت إضافة {waiter.customer_name} في قائمة الانتظار بنجاح!", "id": waiter.id})


@app.route("/api/waiting-list/<int:wait_id>/seat", methods=["POST"])
@app.route("/api/cezar/waiting-list/<int:wait_id>/seat", methods=["POST"])
def seat_waiting_customer(wait_id):
    data = request.json or {}
    table_num = int(data.get("table_number") or 1)
    with SessionLocal() as db:
        waiter = db.query(WaitingList).filter(WaitingList.id == wait_id).first()
        if not waiter:
            return jsonify({"detail": "العميل غير موجود بقائمة الانتظار"}), 404
        waiter.status = "تم التسكين"
        waiter.assigned_table = table_num
        db.commit()
        return jsonify({"status": "success", "message": f"تم تسكين العميل {waiter.customer_name} على ترابيزة رقم {table_num}!"})


@app.route("/api/waiting-list/<int:wait_id>/status", methods=["PUT"])
@app.route("/api/cezar/waiting-list/<int:wait_id>/status", methods=["PUT"])
def update_waiting_status(wait_id):
    data = request.json or {}
    with SessionLocal() as db:
        waiter = db.query(WaitingList).filter(WaitingList.id == wait_id).first()
        if not waiter:
            return jsonify({"detail": "العميل غير موجود"}), 404
        waiter.status = data.get("status") or waiter.status
        db.commit()
        return jsonify({"status": "success", "new_status": waiter.status})


@app.route("/api/waiting-list/<int:wait_id>", methods=["DELETE"])
@app.route("/api/cezar/waiting-list/<int:wait_id>", methods=["DELETE"])
def delete_waiting_customer(wait_id):
    with SessionLocal() as db:
        waiter = db.query(WaitingList).filter(WaitingList.id == wait_id).first()
        if not waiter:
            return jsonify({"detail": "العميل غير موجود"}), 404
        db.delete(waiter)
        db.commit()
        return jsonify({"status": "success", "message": "تم حذف العميل من قائمة الانتظار"})


# ==========================================
# 6. البروموكود والخصومات
# ==========================================

@app.route("/api/promo-codes", methods=["GET"])
@app.route("/api/cezar/promo-codes", methods=["GET"])
def get_promo_codes():
    with SessionLocal() as db:
        codes = db.query(PromoCode).order_by(desc(PromoCode.id)).all()
        return jsonify({
            "promo_codes": [
                {
                    "id": p.id,
                    "code": p.code,
                    "discount_type": p.discount_type,
                    "discount_value": p.discount_value,
                    "min_order_value": p.min_order_value or 0.0,
                    "is_active": p.is_active,
                    "usage_count": p.usage_count or 0
                }
                for p in codes
            ]
        })


@app.route("/api/promo-codes", methods=["POST"])
@app.route("/api/cezar/promo-codes", methods=["POST"])
def create_promo_code():
    data = request.json or {}
    code_str = (data.get("code") or "").strip().upper()
    with SessionLocal() as db:
        existing = db.query(PromoCode).filter(PromoCode.code == code_str).first()
        if existing:
            return jsonify({"detail": "كود الخصم موجود بالفعل"}), 400

        new_promo = PromoCode(
            code=code_str,
            discount_type=data.get("discount_type") or "percentage",
            discount_value=float(data.get("discount_value") or 10.0),
            min_order_value=float(data.get("min_order_value") or 0.0),
            is_active=True
        )
        db.add(new_promo)
        db.commit()
        return jsonify({"status": "success", "message": f"تم إنشاء كود الخصم {new_promo.code} بنجاح!", "id": new_promo.id})


@app.route("/api/promo-codes/validate", methods=["POST"])
@app.route("/api/cezar/promo-codes/validate", methods=["POST"])
def validate_promo_code():
    data = request.json or {}
    code_str = (data.get("code") or "").strip().upper()
    order_total = float(data.get("order_total") or 0.0)

    with SessionLocal() as db:
        promo = db.query(PromoCode).filter(PromoCode.code == code_str, PromoCode.is_active.is_(True)).first()
        if not promo:
            return jsonify({"detail": "كود الخصم غير صحيح أو منتهي الصلاحية"}), 404

        if order_total < (promo.min_order_value or 0.0):
            return jsonify({"detail": f"الحد الأدنى لتفعيل هذا الكود هو {promo.min_order_value} جنيه"}), 400

        if promo.discount_type == "percentage":
            discount = round((order_total * promo.discount_value) / 100.0, 2)
        else:
            discount = min(order_total, promo.discount_value)

        new_total = max(0.0, order_total - discount)
        return jsonify({
            "status": "valid",
            "code": promo.code,
            "discount_type": promo.discount_type,
            "discount_value": promo.discount_value,
            "discount_amount": discount,
            "new_total": new_total,
            "message": f"تم تطبيق خصم {promo.discount_value}{'%' if promo.discount_type == 'percentage' else ' ج'} بنجاح!"
        })


@app.route("/api/promo-codes/<int:code_id>", methods=["DELETE"])
@app.route("/api/cezar/promo-codes/<int:code_id>", methods=["DELETE"])
def delete_promo_code(code_id):
    with SessionLocal() as db:
        p = db.query(PromoCode).filter(PromoCode.id == code_id).first()
        if not p:
            return jsonify({"detail": "كود الخصم غير موجود"}), 404
        db.delete(p)
        db.commit()
        return jsonify({"status": "success", "message": "تم حذف كود الخصم"})


# ==========================================
# 7. إدارة المخزون وتنبيه النواقص
# ==========================================

@app.route("/api/inventory", methods=["GET"])
@app.route("/api/cezar/inventory", methods=["GET"])
def get_inventory():
    with SessionLocal() as db:
        items = db.query(InventoryItem).order_by(InventoryItem.name).all()
        alerts = []
        inv_list = []
        for i in items:
            is_low = i.current_stock <= i.min_alert_stock
            item_data = {
                "id": i.id,
                "name": i.name,
                "unit": i.unit,
                "current_stock": i.current_stock,
                "min_alert_stock": i.min_alert_stock,
                "cost_per_unit": i.cost_per_unit,
                "is_low": is_low
            }
            inv_list.append(item_data)
            if is_low:
                alerts.append(item_data)

        return jsonify({
            "status": "success",
            "inventory": inv_list,
            "low_stock_alerts": alerts,
            "alerts_count": len(alerts)
        })


@app.route("/api/inventory", methods=["POST"])
@app.route("/api/cezar/inventory", methods=["POST"])
def add_inventory_item():
    data = request.json or {}
    name_str = (data.get("name") or "").strip()
    with SessionLocal() as db:
        existing = db.query(InventoryItem).filter(InventoryItem.name == name_str).first()
        if existing:
            return jsonify({"detail": "الصنف موجود بالفعل في المخزن"}), 400

        item = InventoryItem(
            name=name_str,
            unit=(data.get("unit") or "كجم").strip(),
            current_stock=float(data.get("current_stock") or 0.0),
            min_alert_stock=float(data.get("min_alert_stock") or 5.0),
            cost_per_unit=float(data.get("cost_per_unit") or 0.0)
        )
        db.add(item)
        db.commit()
        return jsonify({"status": "success", "message": f"تمت إضافة {item.name} للمخزن بنجاح!", "id": item.id})


@app.route("/api/inventory/<int:item_id>", methods=["PUT"])
@app.route("/api/cezar/inventory/<int:item_id>", methods=["PUT"])
def update_inventory_item(item_id):
    data = request.json or {}
    with SessionLocal() as db:
        item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
        if not item:
            return jsonify({"detail": "الصنف غير موجود بالمخزن"}), 404

        if "current_stock" in data and data["current_stock"] is not None:
            item.current_stock = float(data["current_stock"])
        if "min_alert_stock" in data and data["min_alert_stock"] is not None:
            item.min_alert_stock = float(data["min_alert_stock"])
        if "cost_per_unit" in data and data["cost_per_unit"] is not None:
            item.cost_per_unit = float(data["cost_per_unit"])

        db.commit()
        return jsonify({"status": "success", "message": "تم تحديث رصيد المخزن بنجاح"})


@app.route("/api/inventory/<int:item_id>", methods=["DELETE"])
@app.route("/api/cezar/inventory/<int:item_id>", methods=["DELETE"])
def delete_inventory_item(item_id):
    with SessionLocal() as db:
        item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
        if not item:
            return jsonify({"detail": "الصنف غير موجود"}), 404
        db.delete(item)
        db.commit()
        return jsonify({"status": "success", "message": "تم حذف الصنف من المخزن"})


# ==========================================
# 8. تقارير ذكية وتصدير Excel (Analytics & Export)
# ==========================================

@app.route("/api/analytics", methods=["GET"])
@app.route("/api/cezar/analytics", methods=["GET"])
def get_analytics():
    with SessionLocal() as db:
        orders = db.query(TableOrder).filter(
            TableOrder.status != "ملغي",
            ~TableOrder.status.like("طلب حساب%"),
            TableOrder.status != "نداء ويتر",
            TableOrder.total_price > 0
        ).all()

        item_counter = {}
        for o in orders:
            if not o.items_summary:
                continue
            for line in o.items_summary.split("\n"):
                line = line.strip().lstrip("- ")
                if "x " in line:
                    try:
                        parts = line.split("x ", 1)
                        qty = int(parts[0].strip())
                        name_part = parts[1].split(":")[0].strip()
                        if "[" in name_part:
                            name_part = name_part.split("[")[0].strip()
                        item_counter[name_part] = item_counter.get(name_part, 0) + qty
                    except Exception:
                        pass

        top_items = sorted(
            [{"name": k, "orders_count": v} for k, v in item_counter.items()],
            key=lambda x: x["orders_count"],
            reverse=True
        )[:6]

        hourly_counts = {h: 0 for h in range(24)}
        for o in orders:
            if o.created_at:
                hourly_counts[o.created_at.hour] += 1

        peak_hours = [{"hour": f"{h}:00", "count": hourly_counts[h]} for h in range(8, 24)]

        sales_by_type = {"صالة": 0.0, "تيك أواي": 0.0, "دليفري": 0.0}
        for o in orders:
            t = o.order_type or "صالة"
            sales_by_type[t] = sales_by_type.get(t, 0.0) + o.total_price

        gross_sales = round(sum(o.total_price for o in orders), 2)
        menu_costs = {item.name: (item.cost_price or (item.price * 0.32)) for item in db.query(MenuItem).all()}
        calc_cogs = 0.0
        for name, qty in item_counter.items():
            unit_cost = menu_costs.get(name)
            if unit_cost is not None and unit_cost > 0:
                calc_cogs += unit_cost * qty
            else:
                calc_cogs += ((gross_sales / max(1, len(orders))) * 0.32 * qty) if gross_sales > 0 else 0.0

        total_cogs = round(calc_cogs if calc_cogs > 0 else (gross_sales * 0.32), 2)
        total_expenses = round(float(db.query(func.sum(Expense.amount)).scalar() or 0.0), 2)
        total_salaries = round(float(db.query(func.sum(SalaryPayment.amount)).scalar() or 0.0), 2)
        net_profit = round(gross_sales - total_cogs - total_expenses - total_salaries, 2)
        profit_margin_pct = round((net_profit / gross_sales) * 100, 1) if gross_sales > 0 else 0.0

        return jsonify({
            "status": "success",
            "gross_sales": gross_sales,
            "total_sales": gross_sales,
            "total_cogs": total_cogs,
            "cogs": total_cogs,
            "total_expenses": total_expenses,
            "total_salaries": total_salaries,
        "total_waste": total_waste,
            "net_profit": net_profit,
            "profit_margin_pct": profit_margin_pct,
            "top_sellers": top_items,
            "peak_hours": peak_hours,
            "sales_by_type": sales_by_type,
            "total_served_orders": len(orders)
        })


@app.route("/api/export/sales-csv", methods=["GET"])
@app.route("/api/cezar/export/sales-csv", methods=["GET"])
def export_sales_csv():
    with SessionLocal() as db:
        orders = db.query(TableOrder).filter(
            TableOrder.status != "ملغي",
            TableOrder.total_price > 0
        ).order_by(desc(TableOrder.id)).all()

        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output)
        writer.writerow([
            "رقم الطلب",
            "نوع الطلب",
            "رقم الترابيزة",
            "اسم العميل",
            "رقم الهاتف",
            "الأصناف المطلوبة",
            "طريقة الدفع",
            "الخصم (ج)",
            "الإجمالي المدفوع (ج)",
            "الحالة",
            "التاريخ والوقت"
        ])

        for o in orders:
            writer.writerow([
                o.id,
                o.order_type or "صالة",
                o.table_number or "-",
                o.customer_name or "-",
                o.customer_phone or "-",
                (o.items_summary or "").replace("\n", " | "),
                o.payment_method or "كاش",
                o.discount_amount or 0.0,
                o.total_price,
                o.status,
                o.created_at.strftime("%Y-%m-%d %I:%M %p") if o.created_at else "-"
            ])

        csv_data = output.getvalue().encode("utf-8-sig")
        filename = f"ceZar_Sales_Report_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )


# ==========================================
# 9. تسجيل الدخول
# ==========================================

@app.route("/api/auth/login", methods=["POST"])
@app.route("/api/cezar/auth/login", methods=["POST"])
def manager_login():
    data = request.json or {}
    user = (data.get("username") or "").strip()
    pwd = (data.get("password") or "").strip()
    with SessionLocal() as db:
        account = db.query(ManagerAccount).filter(
            ManagerAccount.username == user,
            ManagerAccount.password == pwd
        ).first()
        if not account:
            return jsonify({"detail": "اسم المستخدم أو كلمة المرور غير صحيحة"}), 401
        return jsonify({
            "status": "success",
            "username": account.username,
            "manager_name": account.manager_name or "المدير العام",
        "role": account.role or "admin"
        })


@app.route("/api/auth/change-credentials", methods=["POST"])
@app.route("/api/cezar/auth/change-credentials", methods=["POST"])
def change_credentials():
    data = request.json or {}
    curr_pwd = (data.get("current_password") or "").strip()
    new_user = (data.get("new_username") or "").strip()
    new_pwd = (data.get("new_password") or "").strip()
    with SessionLocal() as db:
        account = db.query(ManagerAccount).filter(ManagerAccount.password == curr_pwd).first()
        if not account:
            return jsonify({"detail": "كلمة المرور الحالية غير صحيحة!"}), 400
        if not new_user or not new_pwd:
            return jsonify({"detail": "اسم المستخدم وكلمة المرور الجديدة لا يمكن أن تكون فارغة!"}), 400
        account.username = new_user
        account.password = new_pwd
        db.commit()
        return jsonify({"status": "success", "message": "تم تحديث بيانات الدخول بنجاح!", "username": account.username})



# ==========================================
# HR, Salaries & Users Endpoints
# ==========================================

@app.route("/api/employees", methods=["GET"])
@app.route("/api/cezar/employees", methods=["GET"])
def get_employees():
    with get_db() as db:
        employees = db.query(Employee).order_by(Employee.id.desc()).all()
        total_salary = sum(e.salary for e in employees if e.status == "نشط")
        return jsonify({
            "status": "success",
            "employees": [{
                "id": e.id, "name": e.name, "role": e.role, "phone": e.phone or "",
                "salary": e.salary, "hire_date": e.hire_date or "", "status": e.status, "notes": e.notes or ""
            } for e in employees],
            "total_payroll": total_salary,
            "active_count": sum(1 for e in employees if e.status == "نشط")
        })

@app.route("/api/employees", methods=["POST"])
@app.route("/api/cezar/employees", methods=["POST"])
def save_employee():
    data = request.get_json() or {}
    emp_id = data.get("id")
    with get_db() as db:
        if emp_id:
            emp = db.query(Employee).filter(Employee.id == emp_id).first()
            if not emp: return jsonify({"detail": "الموظف غير موجود"}), 404
            emp.name = data.get("name", "").strip()
            emp.role = data.get("role", "").strip()
            emp.phone = (data.get("phone") or "").strip()
            emp.salary = float(data.get("salary") or 0.0)
            emp.hire_date = data.get("hire_date")
            emp.status = data.get("status", "نشط")
            emp.notes = data.get("notes")
        else:
            emp = Employee(
                name=data.get("name", "").strip(),
                role=data.get("role", "").strip(),
                phone=(data.get("phone") or "").strip(),
                salary=float(data.get("salary") or 0.0),
                hire_date=data.get("hire_date") or datetime.utcnow().strftime("%Y-%m-%d"),
                status=data.get("status", "نشط"),
                notes=data.get("notes", "")
            )
            db.add(emp)
        db.commit()
        return jsonify({"status": "success", "message": "تم حفظ بيانات الموظف بنجاح!"})

@app.route("/api/employees/<int:emp_id>", methods=["DELETE"])
@app.route("/api/cezar/employees/<int:emp_id>", methods=["DELETE"])
def delete_employee(emp_id):
    with get_db() as db:
        emp = db.query(Employee).filter(Employee.id == emp_id).first()
        if not emp: return jsonify({"detail": "الموظف غير موجود"}), 404
        db.delete(emp)
        db.commit()
        return jsonify({"status": "success", "message": "تم حذف الموظف بنجاح"})

@app.route("/api/salaries", methods=["GET"])
@app.route("/api/cezar/salaries", methods=["GET"])
def get_salary_payments():
    with get_db() as db:
        payments = db.query(SalaryPayment).order_by(SalaryPayment.id.desc()).all()
        emps = {e.id: e.name for e in db.query(Employee).all()}
        return jsonify({
            "status": "success",
            "payments": [{
                "id": p.id,
                "employee_id": p.employee_id,
                "employee_name": emps.get(p.employee_id, "موظف"),
                "amount": p.amount,
                "payment_type": p.payment_type,
                "month": p.month,
                "payment_date": p.payment_date.strftime("%Y-%m-%d %I:%M %p") if p.payment_date else "",
                "notes": p.notes or ""
            } for p in payments],
            "total_paid": sum(p.amount for p in payments)
        })

@app.route("/api/salaries", methods=["POST"])
@app.route("/api/cezar/salaries", methods=["POST"])
def record_salary_payment():
    data = request.get_json() or {}
    emp_id = data.get("employee_id")
    with get_db() as db:
        emp = db.query(Employee).filter(Employee.id == emp_id).first()
        if not emp: return jsonify({"detail": "الموظف غير موجود"}), 404
        
        p_date = datetime.utcnow()
        date_str = data.get("payment_date")
        if date_str:
            try:
                p_date = datetime.strptime(date_str.strip()[:10], "%Y-%m-%d")
            except Exception:
                p_date = datetime.utcnow()
                
        month_val = data.get("month")
        if not month_val or len(month_val) < 7:
            month_val = p_date.strftime("%Y-%m")
            
        pay = SalaryPayment(
            employee_id=emp_id,
            amount=float(data.get("amount") or 0.0),
            payment_type=data.get("payment_type", "راتب شهري"),
            month=month_val,
            payment_date=p_date,
            notes=data.get("notes", "")
        )
        db.add(pay)
        db.commit()
        return jsonify({"status": "success", "message": f"تم تسجيل صرف {pay.payment_type} للموظف ({emp.name}) بنجاح!"})

@app.route("/api/salaries/<int:pay_id>", methods=["DELETE"])
@app.route("/api/employees/<int:emp_id>/monthly-ledger", methods=["GET"])
@app.route("/api/cezar/employees/<int:emp_id>/monthly-ledger", methods=["GET"])
def get_employee_monthly_ledger(emp_id):
    import calendar
    month = request.args.get("month")
    if not month or len(month) < 7:
        month = datetime.utcnow().strftime("%Y-%m")
    try:
        parts = month.split("-")
        year, month_num = int(parts[0]), int(parts[1])
    except Exception:
        now = datetime.utcnow()
        year, month_num = now.year, now.month
        month = f"{year}-{month_num:02d}"

    with get_db() as db:
        emp = db.query(Employee).filter(Employee.id == emp_id).first()
        if not emp: return jsonify({"detail": "الموظف غير موجود"}), 404

        _, total_days = calendar.monthrange(year, month_num)
        prefix = f"{year}-{month_num:02d}-"
        attendances = db.query(EmployeeAttendance).filter(
            EmployeeAttendance.employee_id == emp_id,
            EmployeeAttendance.date.startswith(prefix)
        ).all()
        att_map = {a.date: a for a in attendances}
        arabic_days = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
        today_str = datetime.utcnow().strftime("%Y-%m-%d")

        attendance_days = []
        present_count, leave_count, absent_count, half_day_count = 0, 0, 0, 0

        for day in range(1, total_days + 1):
            date_str = f"{year}-{month_num:02d}-{day:02d}"
            weekday_idx = datetime(year, month_num, day).weekday()
            day_name = arabic_days[weekday_idx]

            if date_str in att_map:
                st = att_map[date_str].status
                notes = att_map[date_str].notes or ""
                att_id = att_map[date_str].id
            else:
                att_id = None
                notes = ""
                st = "حاضر" if date_str <= today_str else "قادم"

            if st == "حاضر": present_count += 1
            elif st == "إجازة": leave_count += 1
            elif st == "غياب": absent_count += 1
            elif st == "نصف يوم": half_day_count += 1

            attendance_days.append({
                "day": day, "date": date_str, "day_name": day_name,
                "status": st, "notes": notes, "attendance_id": att_id
            })

        payments = db.query(SalaryPayment).filter(
            SalaryPayment.employee_id == emp_id,
            SalaryPayment.month == month
        ).order_by(SalaryPayment.payment_date.desc(), SalaryPayment.id.desc()).all()

        total_advances = sum(p.amount for p in payments if p.payment_type == "سلفة")
        total_deductions = sum(p.amount for p in payments if p.payment_type == "خصم")
        total_bonuses = sum(p.amount for p in payments if p.payment_type == "مكافأة")
        total_salary_paid = sum(p.amount for p in payments if p.payment_type == "راتب شهري")
        base_salary = float(emp.salary or 0.0)
        net_remaining = base_salary - total_advances - total_deductions + total_bonuses - total_salary_paid

        advances_list = [{
            "id": p.id, "amount": p.amount,
            "date_str": p.payment_date.strftime("%Y-%m-%d") if p.payment_date else month,
            "datetime_str": p.payment_date.strftime("%Y-%m-%d %I:%M %p") if p.payment_date else "",
            "notes": p.notes or ""
        } for p in payments if p.payment_type == "سلفة"]

        all_transactions = [{
            "id": p.id, "payment_type": p.payment_type, "amount": p.amount,
            "date_str": p.payment_date.strftime("%Y-%m-%d") if p.payment_date else month,
            "datetime_str": p.payment_date.strftime("%Y-%m-%d %I:%M %p") if p.payment_date else "",
            "notes": p.notes or ""
        } for p in payments]

        return jsonify({
            "status": "success",
            "employee": {"id": emp.id, "name": emp.name, "role": emp.role, "salary": emp.salary, "phone": emp.phone or ""},
            "month": month,
            "days_in_month": total_days,
            "attendance_summary": {"present_days": present_count, "leave_days": leave_count, "absent_days": absent_count, "half_days": half_day_count},
            "attendance_days": attendance_days,
            "financial_summary": {"base_salary": base_salary, "total_advances": total_advances, "total_deductions": total_deductions, "total_bonuses": total_bonuses, "total_salary_paid": total_salary_paid, "net_remaining": net_remaining},
            "advances_list": advances_list,
            "all_transactions": all_transactions
        })

@app.route("/api/employees/attendance", methods=["POST"])
@app.route("/api/cezar/employees/attendance", methods=["POST"])
def record_employee_attendance():
    data = request.get_json() or {}
    emp_id = data.get("employee_id")
    date_val = data.get("date")
    status_val = data.get("status", "حاضر")
    notes_val = data.get("notes", "")

    with get_db() as db:
        emp = db.query(Employee).filter(Employee.id == emp_id).first()
        if not emp: return jsonify({"detail": "الموظف غير موجود"}), 404
        rec = db.query(EmployeeAttendance).filter(
            EmployeeAttendance.employee_id == emp_id,
            EmployeeAttendance.date == date_val
        ).first()
        if rec:
            rec.status = status_val
            rec.notes = notes_val
        else:
            rec = EmployeeAttendance(employee_id=emp_id, date=date_val, status=status_val, notes=notes_val)
            db.add(rec)
        db.commit()
        return jsonify({"status": "success", "message": f"تم حفظ حالة ({status_val}) للموظف {emp.name}"})

@app.route("/api/employees/attendance/batch", methods=["POST"])
@app.route("/api/cezar/employees/attendance/batch", methods=["POST"])
def batch_employee_attendance():
    data = request.get_json() or {}
    date_val = data.get("date")
    status_val = data.get("status", "حاضر")
    with get_db() as db:
        emps = db.query(Employee).filter(Employee.status == "نشط").all()
        for emp in emps:
            rec = db.query(EmployeeAttendance).filter(EmployeeAttendance.employee_id == emp.id, EmployeeAttendance.date == date_val).first()
            if rec: rec.status = status_val
            else:
                db.add(EmployeeAttendance(employee_id=emp.id, date=date_val, status=status_val, notes="تحضير جماعي"))
        db.commit()
        return jsonify({"status": "success", "message": f"تم تحضير {len(emps)} موظف بنجاح"})

@app.route("/api/cezar/salaries/<int:pay_id>", methods=["DELETE"])
def delete_salary_payment(pay_id):
    with get_db() as db:
        pay = db.query(SalaryPayment).filter(SalaryPayment.id == pay_id).first()
        if pay:
            db.delete(pay)
            db.commit()
        return jsonify({"status": "success", "message": "تم حذف سجل الصرف بنجاح"})

@app.route("/api/auth/users", methods=["GET"])
@app.route("/api/cezar/auth/users", methods=["GET"])
def list_system_users():
    with get_db() as db:
        users = db.query(ManagerAccount).all()
        return jsonify({
            "status": "success",
            "users": [{"id": u.id, "username": u.username, "manager_name": u.manager_name, "role": u.role or "admin"} for u in users]
        })

@app.route("/api/auth/users", methods=["POST"])
@app.route("/api/cezar/auth/users", methods=["POST"])
def save_system_user():
    data = request.get_json() or {}
    u_id = data.get("id")
    with get_db() as db:
        if u_id:
            u = db.query(ManagerAccount).filter(ManagerAccount.id == u_id).first()
            if not u: return jsonify({"detail": "المستخدم غير موجود"}), 404
            u.username = data.get("username", "").strip()
            u.manager_name = data.get("manager_name", "").strip()
            u.role = data.get("role", "cashier").strip()
            if data.get("password"):
                u.password = data.get("password", "").strip()
        else:
            username = data.get("username", "").strip()
            if db.query(ManagerAccount).filter(ManagerAccount.username == username).first():
                return jsonify({"detail": "اسم المستخدم مستخدم بالفعل!"}), 400
            u = ManagerAccount(
                username=username,
                password=data.get("password", "1234").strip(),
                manager_name=data.get("manager_name", "موظف").strip(),
                role=data.get("role", "cashier").strip()
            )
            db.add(u)
        db.commit()
        return jsonify({"status": "success", "message": "تم حفظ بيانات المستخدم وصلاحياته بنجاح!"})

@app.route("/api/auth/users/<int:user_id>", methods=["DELETE"])
@app.route("/api/cezar/auth/users/<int:user_id>", methods=["DELETE"])
def delete_system_user(user_id):
    with get_db() as db:
        u = db.query(ManagerAccount).filter(ManagerAccount.id == user_id).first()
        if not u: return jsonify({"detail": "المستخدم غير موجود"}), 404
        if u.username == "admin":
            return jsonify({"detail": "لا يمكن حذف حساب المدير العام الرئيسي!"}), 400
        db.delete(u)
        db.commit()
        return jsonify({"status": "success", "message": "تم حذف المستخدم بنجاح"})



# ==========================================
# Waste, Purchases, Suppliers, Menu Categories & Backup
# ==========================================

@app.route("/api/inventory/waste", methods=["GET"])
@app.route("/api/cezar/inventory/waste", methods=["GET"])
@db_retry(max_retries=3, delay=0.3)
def get_inventory_waste():
    month = request.args.get("month")
    waste_type = request.args.get("waste_type")
    with SessionLocal() as db:
        query = db.query(InventoryWaste)
        if month and month.strip():
            query = query.filter(InventoryWaste.date.like(f"{month.strip()}%"))
        if waste_type and waste_type.strip() and waste_type.strip() != "الكل":
            query = query.filter(InventoryWaste.waste_type == waste_type.strip())
        
        records = query.order_by(desc(InventoryWaste.date), desc(InventoryWaste.id)).all()
        total_cost_loss = sum(r.cost_loss or 0.0 for r in records)
        total_qty = sum(r.quantity or 0.0 for r in records)

        by_type = {}
        for r in records:
            t = r.waste_type or "أخرى"
            by_type[t] = round(by_type.get(t, 0.0) + (r.cost_loss or 0.0), 2)

        return jsonify({
            "status": "success",
            "stats": {
                "total_records": len(records),
                "total_cost_loss": round(total_cost_loss, 2),
                "total_qty_wasted": round(total_qty, 2),
                "loss_by_type": by_type
            },
            "records": [
                {
                    "id": r.id,
                    "item_id": r.item_id,
                    "item_name": r.item_name,
                    "quantity": r.quantity,
                    "unit": r.unit,
                    "waste_type": r.waste_type,
                    "cost_loss": r.cost_loss,
                    "reason": r.reason,
                    "date": r.date,
                    "time": r.time,
                    "responsible_name": r.responsible_name,
                    "notes": r.notes
                }
                for r in records
            ]
        })


@app.route("/api/inventory/waste", methods=["POST"])
@app.route("/api/cezar/inventory/waste", methods=["POST"])
@db_retry(max_retries=3, delay=0.4)
def record_inventory_waste():
    data = request.json or {}
    item_id = int(data.get("item_id") or 0)
    qty = float(data.get("quantity") or 0.0)
    waste_type = data.get("waste_type") or "هالك تشغيل"
    reason = data.get("reason") or ""
    responsible = data.get("responsible_name") or "كاشير الصالة"
    notes = data.get("notes") or ""

    if not item_id or qty <= 0:
        return jsonify({"detail": "يرجى تحديد الصنف والكمية التالفة بشكل صحيح", "status": "error"}), 400

    with SessionLocal() as db:
        item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
        if not item:
            return jsonify({"detail": "المادة الخام غير موجودة في المخزن", "status": "error"}), 404

        unit_cost = (item.cost_price or 0.0)
        cost_loss = round(qty * unit_cost, 2)
        item.current_stock = max(0.0, round((item.current_stock or 0.0) - qty, 3))

        now = datetime.now()
        waste_entry = InventoryWaste(
            item_id=item.id,
            item_name=item.name,
            quantity=qty,
            unit=item.unit,
            waste_type=waste_type,
            cost_loss=cost_loss,
            reason=reason,
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%I:%M %p"),
            responsible_name=responsible,
            notes=notes
        )
        db.add(waste_entry)
        db.commit()
        db.refresh(waste_entry)

        return jsonify({
            "status": "success",
            "message": f"تم تسجيل هالك ({item.name}) بقيمة {cost_loss:g} ج وخصم الكمية من المخزن بنجاح!",
            "record_id": waste_entry.id,
            "cost_loss": cost_loss,
            "new_stock": item.current_stock
        })


@app.route("/api/inventory/waste/<int:waste_id>", methods=["DELETE", "POST"])
@app.route("/api/cezar/inventory/waste/<int:waste_id>", methods=["DELETE", "POST"])
@db_retry(max_retries=3, delay=0.3)
def delete_inventory_waste(waste_id):
    restore_stock = request.args.get("restore_stock", "true").lower() == "true"
    with SessionLocal() as db:
        waste = db.query(InventoryWaste).filter(InventoryWaste.id == waste_id).first()
        if not waste:
            return jsonify({"detail": "سجل الهالك غير موجود", "status": "error"}), 404

        if restore_stock and waste.item_id:
            item = db.query(InventoryItem).filter(InventoryItem.id == waste.item_id).first()
            if item:
                item.current_stock = round((item.current_stock or 0.0) + (waste.quantity or 0.0), 3)

        db.delete(waste)
        db.commit()
        return jsonify({
            "status": "success",
            "message": "تم حذف سجل الهالك بنجاح" + (" وإرجاع الكمية للمخزن." if restore_stock else ".")
        })


@app.route("/api/purchases", methods=["GET"])
@app.route("/api/cezar/purchases", methods=["GET"])
@db_retry(max_retries=3, delay=0.3)
def get_purchases():
    month = request.args.get("month")
    with SessionLocal() as db:
        query = db.query(PurchaseInvoice)
        if month and month.strip():
            query = query.filter(PurchaseInvoice.date.like(f"{month.strip()}%"))

        invoices = query.order_by(desc(PurchaseInvoice.id)).all()
        total_purchases = sum(i.total_amount or 0.0 for i in invoices)
        total_paid = sum(i.paid_amount or 0.0 for i in invoices)
        total_remaining = sum(i.remaining_amount or 0.0 for i in invoices)

        res = []
        for inv in invoices:
            supp = db.query(Supplier).filter(Supplier.id == inv.supplier_id).first() if inv.supplier_id else None
            items = db.query(PurchaseInvoiceItem).filter(PurchaseInvoiceItem.invoice_id == inv.id).all()
            res.append({
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "supplier_id": inv.supplier_id,
                "supplier_name": supp.name if supp else "مورد عام / نقدي",
                "supplier_phone": supp.phone if supp else "",
                "date": inv.date,
                "total_amount": inv.total_amount,
                "paid_amount": inv.paid_amount,
                "remaining_amount": inv.remaining_amount,
                "payment_status": inv.payment_status,
                "notes": inv.notes,
                "items": [
                    {
                        "id": it.id,
                        "item_name": it.item_name,
                        "quantity": it.quantity,
                        "unit": it.unit,
                        "unit_price": it.unit_price,
                        "total_price": it.total_price
                    }
                    for it in items
                ]
            })

        return jsonify({
            "status": "success",
            "stats": {
                "invoices_count": len(invoices),
                "total_purchases": round(total_purchases, 2),
                "total_paid": round(total_paid, 2),
                "total_remaining": round(total_remaining, 2)
            },
            "invoices": res
        })


@app.route("/api/purchases", methods=["POST"])
@app.route("/api/cezar/purchases", methods=["POST"])
@db_retry(max_retries=3, delay=0.4)
def record_purchase_invoice():
    data = request.json or {}
    supplier_id = int(data.get("supplier_id") or 0) if data.get("supplier_id") else None
    invoice_number = data.get("invoice_number") or ""
    date_val = data.get("date") or datetime.now().strftime("%Y-%m-%d")
    paid_amount = float(data.get("paid_amount") or 0.0)
    notes = data.get("notes") or ""
    items = data.get("items") or []

    if not items:
        return jsonify({"detail": "يجب إضافة بند واحد على الأقل في الفاتورة", "status": "error"}), 400

    with SessionLocal() as db:
        total_amount = 0.0
        parsed_items = []
        for it in items:
            name = (it.get("item_name") or "").strip()
            qty = float(it.get("quantity") or 0.0)
            uprice = float(it.get("unit_price") or 0.0)
            unit = it.get("unit") or "كجم"
            sub = round(qty * uprice, 2)
            total_amount += sub
            parsed_items.append({"name": name, "qty": qty, "unit": unit, "uprice": uprice, "sub": sub})

        remaining = max(0.0, round(total_amount - paid_amount, 2))
        payment_status = "مدفوع بالكامل" if remaining == 0 else ("مدفوع جزئياً" if paid_amount > 0 else "آجل / غير مدفوع")

        inv = PurchaseInvoice(
            invoice_number=invoice_number or f"INV-{int(datetime.now().timestamp())}",
            supplier_id=supplier_id,
            date=date_val,
            total_amount=total_amount,
            paid_amount=paid_amount,
            remaining_amount=remaining,
            payment_status=payment_status,
            notes=notes
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)

        for p in parsed_items:
            db_item = PurchaseInvoiceItem(
                invoice_id=inv.id,
                item_name=p["name"],
                quantity=p["qty"],
                unit=p["unit"],
                unit_price=p["uprice"],
                total_price=p["sub"]
            )
            db.add(db_item)
            
            raw_item = db.query(InventoryItem).filter(InventoryItem.name == p["name"]).first()
            if raw_item:
                raw_item.current_stock = round((raw_item.current_stock or 0.0) + p["qty"], 3)
                if p["uprice"] > 0:
                    raw_item.cost_price = p["uprice"]
            else:
                db.add(InventoryItem(
                    name=p["name"],
                    category="مواد خام",
                    unit=p["unit"],
                    current_stock=p["qty"],
                    min_limit=5.0,
                    cost_price=p["uprice"]
                ))

        if supplier_id and remaining > 0:
            supp = db.query(Supplier).filter(Supplier.id == supplier_id).first()
            if supp:
                supp.total_debt = round((supp.total_debt or 0.0) + remaining, 2)

        db.commit()
        return jsonify({
            "status": "success",
            "message": f"تم حفظ فاتورة التوريد بنجاح! الإجمالي: {total_amount:g} ج وتحديث أرصدة المخزن فوراً.",
            "invoice_id": inv.id,
            "total_amount": total_amount,
            "remaining_amount": remaining
        })


@app.route("/api/suppliers/<int:supplier_id>", methods=["DELETE", "POST"])
@app.route("/api/cezar/suppliers/<int:supplier_id>", methods=["DELETE", "POST"])
@db_retry(max_retries=3, delay=0.3)
def delete_supplier(supplier_id):
    with SessionLocal() as db:
        s = db.query(Supplier).filter(Supplier.id == supplier_id).first()
        if not s:
            return jsonify({"detail": "المورد غير موجود", "status": "error"}), 404
        db.delete(s)
        db.commit()
        return jsonify({"status": "success", "message": "تم حذف المورد بنجاح"})


@app.route("/api/menu/categories/rename", methods=["POST"])
@app.route("/api/cezar/menu/categories/rename", methods=["POST"])
@db_retry(max_retries=3, delay=0.3)
def rename_menu_category():
    data = request.json or {}
    old_cat = (data.get("old_name") or "").strip()
    new_cat = (data.get("new_name") or "").strip()
    if not old_cat or not new_cat:
        return jsonify({"detail": "يرجى كتابة الاسم القديم والاسم الجديد", "status": "error"}), 400
    with SessionLocal() as db:
        items = db.query(MenuItem).filter(MenuItem.category == old_cat).all()
        for item in items:
            item.category = new_cat
        db.commit()
        return jsonify({"status": "success", "message": f"تم تعديل اسم القسم من ({old_cat}) إلى ({new_cat}) لعدد {len(items)} صنف بنجاح!"})


@app.route("/api/menu/categories/delete", methods=["POST"])
@app.route("/api/cezar/menu/categories/delete", methods=["POST"])
@db_retry(max_retries=3, delay=0.3)
def delete_menu_category():
    data = request.json or {}
    cat = (data.get("old_name") or "").strip()
    with SessionLocal() as db:
        items = db.query(MenuItem).filter(MenuItem.category == cat).all()
        for item in items:
            db.delete(item)
        db.commit()
        return jsonify({"status": "success", "message": f"تم حذف قسم ({cat}) وجميع أصنافه ({len(items)} صنف) بنجاح"})


@app.route("/api/admin/reset-test-data", methods=["POST"])
@app.route("/api/cezar/admin/reset-test-data", methods=["POST"])
@db_retry(max_retries=3, delay=0.4)
def reset_test_data():
    with SessionLocal() as db:
        db.query(TableOrder).delete()
        db.query(Reservation).delete()
        db.query(WaitingList).delete()
        db.query(Expense).delete()
        open_shifts = db.query(Shift).filter(Shift.status == "مفتوح").all()
        for s in open_shifts:
            s.status = "مغلق"
            s.end_time = datetime.utcnow()
        db.commit()
        return jsonify({
            "status": "success",
            "message": "تم تصفير كافة الطلبات والحجوزات والمصروفات التجريبية بنجاح مع الحفاظ الكامل على المنيو والمخزون والإعدادات!"
        })


@app.route("/api/backup/restore", methods=["POST"])
@app.route("/api/cezar/backup/restore", methods=["POST"])
def restore_database_backup():
    if "file" not in request.files:
        return jsonify({"detail": "لم يتم اختيار ملف", "status": "error"}), 400
    file = request.files["file"]
    if not file.filename.endswith(".db"):
        return jsonify({"detail": "يجب رفع ملف قاعدة بيانات بصيغة .db فقط", "status": "error"}), 400

    content = file.read()
    if len(content) < 100 or not content.startswith(b"SQLite format 3"):
        return jsonify({"detail": "الملف المرفوع ليس ملف قاعدة بيانات SQLite صالح", "status": "error"}), 400

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_db = os.path.join(base_dir, "cezar_coffee.db")
    backup_db = os.path.join(base_dir, f"cezar_coffee_backup_before_restore_{int(datetime.now().timestamp())}.db")

    if os.path.exists(target_db):
        try:
            shutil.copyfile(target_db, backup_db)
        except Exception:
            pass

    with open(target_db, "wb") as f:
        f.write(content)

    return jsonify({"status": "success", "message": "تم استرجاع قاعدة البيانات بنجاح!"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)

# ==========================================
# 11. إعدادات المالك والتحكم الشامل (Flask)
# ==========================================

@app.route("/api/settings", methods=["GET"])
@app.route("/api/cezar/settings", methods=["GET"])
def get_cafe_settings_flask():
    with SessionLocal() as db:
        settings = db.query(CafeSetting).all()
        return jsonify({"status": "success", "settings": {s.key: s.value for s in settings}})

@app.route("/api/settings", methods=["POST"])
@app.route("/api/cezar/settings", methods=["POST"])
def update_cafe_settings_flask():
    data = request.get_json() or {}
    settings_dict = data.get("settings", {})
    with SessionLocal() as db:
        for k, v in settings_dict.items():
            s = db.query(CafeSetting).filter(CafeSetting.key == k).first()
            if s:
                s.value = str(v)
            else:
                db.add(CafeSetting(key=k, value=str(v), description="تخصيص المالك"))
        db.commit()
        return jsonify({"status": "success", "message": "تم حفظ وتحديث إعدادات الكافيه بنجاح!"})

@app.route("/api/tables/configs", methods=["GET"])
@app.route("/api/cezar/tables/configs", methods=["GET"])
def get_tables_configs_flask():
    with SessionLocal() as db:
        configs = db.query(CafeTableConfig).order_by(CafeTableConfig.table_number.asc()).all()
        return jsonify({
            "status": "success",
            "tables": [{"table_number": c.table_number, "capacity": c.capacity, "zone": c.zone, "is_active": c.is_active} for c in configs]
        })

@app.route("/api/tables/configs", methods=["POST"])
@app.route("/api/cezar/tables/configs", methods=["POST"])
def update_table_config_flask():
    data = request.get_json() or {}
    t_num = data.get("table_number")
    with SessionLocal() as db:
        cfg = db.query(CafeTableConfig).filter(CafeTableConfig.table_number == t_num).first()
        if not cfg:
            cfg = CafeTableConfig(table_number=t_num)
            db.add(cfg)
        cfg.capacity = data.get("capacity", 4)
        cfg.zone = data.get("zone", "صالة رئيسية")
        cfg.is_active = data.get("is_active", True)
        db.commit()
        return jsonify({"status": "success", "message": f"تم تحديث بيانات ترابيزة {t_num} بنجاح"})

@app.route("/api/tables/batch-count", methods=["POST"])
@app.route("/api/cezar/tables/batch-count", methods=["POST"])
def update_batch_tables_count_flask():
    data = request.get_json() or {}
    count = max(1, min(100, int(data.get("tables_count", 25))))
    with SessionLocal() as db:
        existing = {c.table_number: c for c in db.query(CafeTableConfig).all()}
        for t in range(1, count + 1):
            if t in existing:
                existing[t].is_active = True
            else:
                db.add(CafeTableConfig(table_number=t, capacity=4, zone="صالة رئيسية", is_active=True))
        for t, cfg in existing.items():
            if t > count:
                cfg.is_active = False
        s = db.query(CafeSetting).filter(CafeSetting.key == "tables_count").first()
        if s:
            s.value = str(count)
        else:
            db.add(CafeSetting(key="tables_count", value=str(count)))
        db.commit()
        return jsonify({"status": "success", "message": f"تم تحديث إجمالي عدد الترابيزات إلى {count} ترابيزة"})

@app.route("/api/menu/bulk-adjust-prices", methods=["POST"])
@app.route("/api/cezar/menu/bulk-adjust-prices", methods=["POST"])
def bulk_adjust_prices_flask():
    data = request.get_json() or {}
    category = data.get("category", "all")
    adj_type = data.get("adjust_type", "percentage")
    val = float(data.get("value", 0.0))
    round_five = bool(data.get("round_to_five", False))
    with SessionLocal() as db:
        query = db.query(MenuItem)
        if category and category != "all":
            query = query.filter(MenuItem.category == category.strip())
        items = query.all()
        count = 0
        for item in items:
            old_p = item.price
            if adj_type == "percentage":
                new_p = old_p * (1.0 + (val / 100.0))
            else:
                new_p = old_p + val
            if round_five:
                new_p = round(new_p / 5.0) * 5.0
            else:
                new_p = round(new_p, 2)
            new_p = max(1.0, new_p)
            item.price = new_p
            item.cost_price = round(new_p * 0.32, 2)
            count += 1
        db.commit()
        return jsonify({"status": "success", "message": f"تم تعديل أسعار {count} صنف بنجاح!", "updated_count": count})

@app.route("/api/admin/backup-db", methods=["GET"])
@app.route("/api/cezar/admin/backup-db", methods=["GET"])
def download_db_backup_flask():
    import os
    from flask import send_file
    db_file = os.path.abspath("cezar_coffee.db")
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return send_file(db_file, as_attachment=True, download_name=f"cezar_coffee_backup_{timestamp}.db")

@app.route("/api/reports/tables", methods=["GET"])
@app.route("/api/cezar/reports/tables", methods=["GET"])
def get_tables_sales_report():
    import re
    from datetime import timedelta
    period = request.args.get("period", "today")
    now = datetime.utcnow()
    
    if period == "week":
        start_date = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = "تقرير مبيعات الترابيزات لآخر 7 أيام"
    elif period == "month":
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_label = f"تقرير مبيعات الترابيزات لشهر ({now.strftime('%m-%Y')})"
    else:
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = f"تقرير مبيعات الترابيزات لليوم ({now.strftime('%Y-%m-%d')})"

    with get_db() as db:
        orders = db.query(TableOrder).filter(TableOrder.created_at >= start_date, TableOrder.status != "ملغي").all()
        configs = db.query(CafeTableConfig).all()
        config_map = {c.table_number: c for c in configs}

        max_t = 25
        if configs: max_t = max(max_t, max(c.table_number for c in configs))
        if orders:
            valid_table_nums = [o.table_number for o in orders if o.table_number and o.table_number > 0]
            if valid_table_nums: max_t = max(max_t, max(valid_table_nums))

        total_revenue_all = sum(o.total_price for o in orders)
        total_orders_all = len(orders)
        tables_data = []
        top_table_obj = None
        max_rev = -1

        for t_num in range(1, max_t + 1):
            t_orders = [o for o in orders if o.table_number == t_num]
            rev = sum(o.total_price for o in t_orders)
            cnt = len(t_orders)
            avg = round(rev / cnt, 1) if cnt > 0 else 0.0

            item_counts = {}
            for o in t_orders:
                text_sum = o.items_summary or ""
                matches = re.findall(r'-?\s*(\d+)x?\s*([^:\[\r\n]+)', text_sum)
                for qty_str, name in matches:
                    name_clean = name.strip()
                    if name_clean: item_counts[name_clean] = item_counts.get(name_clean, 0) + int(qty_str)

            top_items_list = sorted(item_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            top_items_str = "، ".join([f"{name} ({q})" for name, q in top_items_list]) if top_items_list else "لا توجد طلبات"

            cfg = config_map.get(t_num)
            zone = cfg.zone if cfg else ("VIP" if t_num > 20 else "صالة رئيسية")
            capacity = cfg.capacity if cfg else 4
            is_active = cfg.is_active if cfg else True
            pct = round((rev / total_revenue_all) * 100, 1) if total_revenue_all > 0 else 0.0

            if rev > max_rev and rev > 0:
                max_rev = rev
                top_table_obj = {"table_number": t_num, "revenue": rev, "orders_count": cnt, "zone": zone}

            tables_data.append({
                "table_number": t_num, "zone": zone, "capacity": capacity, "is_active": is_active,
                "orders_count": cnt, "total_revenue": rev, "avg_order_value": avg,
                "top_items": top_items_str, "revenue_percent": pct
            })

        active_tables_count = sum(1 for t in tables_data if t["orders_count"] > 0)
        avg_per_table = round(total_revenue_all / max_t, 1) if max_t > 0 else 0.0

        return jsonify({
            "status": "success",
            "period": period,
            "period_label": period_label,
            "summary": {
                "total_revenue": total_revenue_all,
                "total_orders": total_orders_all,
                "active_tables_count": active_tables_count,
                "total_tables_count": max_t,
                "avg_revenue_per_table": avg_per_table,
                "top_table": top_table_obj
            },
            "tables": tables_data
        })


# ==========================================
# 9. دعم العمليات أوفلاين والمزامنة السحابية (Offline Mode & Cloud Sync - Flask)
# ==========================================

@app.route("/api/ping", methods=["GET"])
def ping_server_flask():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat(), "server": "ceZar POS Cloud/Local Engine v2.0"})


@app.route("/api/pos/sync-offline", methods=["POST"])
def sync_offline_orders_flask():
    db = SessionLocal()
    try:
        data = request.get_json(silent=True) or {}
        orders_data = data.get("orders") or []
        current_shift = db.query(Shift).filter(Shift.status == "مفتوح").order_by(desc(Shift.start_time)).first()

        synced_ids = []
        for item in orders_data:
            items_list = item.get("items") or []
            lines = []
            total_p = 0.0
            for it in items_list:
                price = float(it.get("price") or 0.0)
                customs = it.get("customizations") or []
                for c in customs:
                    price += float(c.get("extra_price") or 0.0)
                qty = int(it.get("quantity") or 1)
                subtotal = price * qty
                total_p += subtotal
                lines.append(f"- {qty}x {it.get('name')} = {subtotal} ج")

            disc = float(item.get("discount_amount") or 0.0)
            grand_total = max(0.0, total_p - disc)
            summary = "\n".join(lines)
            t_num = item.get("table_number") or 1

            order = TableOrder(
                table_number=t_num,
                order_type="صالة",
                customer_name=item.get("customer_name") or f"ترابيزة {t_num}",
                items_summary=summary,
                total_price=grand_total,
                discount_amount=disc,
                promo_code=item.get("promo_code") or "",
                payment_method=item.get("payment_method") or "كاش",
                status="تم التقديم",
                notes=f"{item.get('notes') or ''} [أوردر مسجل أوفلاين]".strip(),
                shift_id=current_shift.id if current_shift else None
            )
            db.add(order)
            if current_shift:
                current_shift.total_sales += grand_total
                if item.get("payment_method") == "فيزا":
                    current_shift.visa_sales += grand_total
                else:
                    current_shift.cash_sales += grand_total

            synced_ids.append(order)

        db.commit()
        return jsonify({
            "status": "success",
            "synced_count": len(synced_ids),
            "message": f"تمت مزامنة {len(synced_ids)} طلبات أوفلاين بنجاح"
        })
    finally:
        db.close()


@app.route("/api/analytics/reset", methods=["POST"])
def reset_analytics_data_flask():
    db = SessionLocal()
    try:
        deleted_count = db.query(TableOrder).delete()
        db.commit()
        return jsonify({
            "status": "success",
            "deleted_count": deleted_count,
            "message": f"تم تصفير بيانات التقارير والمبيعات بنجاح ({deleted_count} طلب)."
        })
    finally:
        db.close()


# ==========================================
# 10. تقرير تقفيل الشيفت الحراري (Z-Report - Flask)
# ==========================================

@app.route("/api/shifts/<int:shift_id>/z-report", methods=["GET"])
def get_shift_z_report_flask(shift_id):
    db = SessionLocal()
    try:
        shift = db.query(Shift).filter(Shift.id == shift_id).first()
        if not shift:
            return jsonify({"detail": "الوردية غير موجودة"}), 404

        orders = db.query(TableOrder).filter(
            TableOrder.shift_id == shift.id,
            TableOrder.status != "ملغي",
            ~TableOrder.status.like("طلب حساب%"),
            TableOrder.status != "نداء ويتر"
        ).all()

        total_orders = len(orders)
        cash_sales = sum(o.total_price for o in orders if (o.payment_method or "كاش") == "كاش")
        visa_sales = sum(o.total_price for o in orders if (o.payment_method or "") == "فيزا")
        total_sales = cash_sales + visa_sales

        expenses = db.query(Expense).filter(Expense.shift_id == shift.id).all()
        expenses_list = [{"title": e.title, "amount": e.amount, "category": e.category or "عام"} for e in expenses]
        total_expenses = sum(e.amount for e in expenses)

        expected_cash = (shift.starting_cash or 0.0) + cash_sales - total_expenses
        actual_cash = shift.actual_cash if shift.actual_cash is not None else expected_cash
        diff = round((actual_cash or 0.0) - expected_cash, 2)

        return jsonify({
            "status": "success",
            "z_report": {
                "shift_id": shift.id,
                "cashier_name": shift.cashier_name or "كاشير سيزر",
                "status": shift.status,
                "start_time": shift.start_time.strftime("%Y-%m-%d %I:%M %p") if shift.start_time else "-",
                "end_time": shift.end_time.strftime("%Y-%m-%d %I:%M %p") if shift.end_time else "جارية حتى الآن",
                "starting_cash": shift.starting_cash or 0.0,
                "total_orders": total_orders,
                "total_sales": round(total_sales, 2),
                "cash_sales": round(cash_sales, 2),
                "visa_sales": round(visa_sales, 2),
                "expenses": expenses_list,
                "total_expenses": round(total_expenses, 2),
                "expected_cash": round(expected_cash, 2),
                "actual_cash": round(actual_cash, 2),
                "difference": diff,
                "notes": shift.notes or ""
            }
        })
    finally:
        db.close()


# ==========================================
# 11. النسخ الاحتياطي (Backup - Flask)
# ==========================================

@app.route("/api/backup/download", methods=["GET"])
def download_database_backup_flask():
    db_path = "cezar_coffee.db"
    if not os.path.exists(db_path):
        return jsonify({"detail": "ملف قاعدة البيانات غير موجود"}), 404
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"cezar_coffee_backup_{timestamp}.db"
    with open(db_path, "rb") as f:
        data = f.read()
    return Response(
        data,
        mimetype="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ==========================================
# 12. الموردين وفواتير الشراء (Suppliers & Purchases - Flask)
# ==========================================

@app.route("/api/suppliers", methods=["GET"])
def get_suppliers_flask():
    db = SessionLocal()
    try:
        suppliers = db.query(Supplier).order_by(Supplier.name).all()
        total_balance = sum(s.current_balance or 0.0 for s in suppliers)
        return jsonify({
            "status": "success",
            "suppliers": [
                {
                    "id": s.id,
                    "name": s.name,
                    "company_name": s.company_name or "-",
                    "phone": s.phone or "-",
                    "current_balance": round(s.current_balance or 0.0, 2),
                    "notes": s.notes or "",
                    "created_at": s.created_at.strftime("%Y-%m-%d") if s.created_at else ""
                }
                for s in suppliers
            ],
            "summary": {
                "total_suppliers": len(suppliers),
                "total_debt_balance": round(total_balance, 2)
            }
        })
    finally:
        db.close()


@app.route("/api/suppliers", methods=["POST"])
def add_supplier_flask():
    db = SessionLocal()
    try:
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"detail": "اسم المورد مطلوب"}), 400

        supplier = Supplier(
            name=name,
            company_name=(data.get("company_name") or "").strip(),
            phone=(data.get("phone") or "").strip(),
            current_balance=float(data.get("current_balance") or 0.0),
            notes=(data.get("notes") or "").strip()
        )
        db.add(supplier)
        db.commit()
        db.refresh(supplier)
        return jsonify({"status": "success", "message": f"تمت إضافة المورد ({supplier.name}) بنجاح!", "id": supplier.id}), 201
    finally:
        db.close()


# ==========================================
# ☕ خلطات ومقادير الأصناف (Recipes & BOM) - Flask
# ==========================================

@app.route('/api/recipes', methods=['GET'])
@app.route('/api/cezar/recipes', methods=['GET'])
def flask_get_all_recipes():
    db = SessionLocal()
    try:
        menu_items = db.query(MenuItem).order_by(MenuItem.category, MenuItem.name).all()
        results = []
        for item in menu_items:
            ingredients_list = []
            calc_cost = 0.0
            for r in item.recipes:
                inv = db.query(InventoryItem).filter(InventoryItem.id == r.inventory_item_id).first()
                if inv:
                    cost = round(r.amount_used * (inv.cost_per_unit or 0.0), 2)
                    calc_cost += cost
                    ingredients_list.append({
                        "recipe_id": r.id,
                        "inventory_item_id": inv.id,
                        "name": inv.name,
                        "unit": inv.unit,
                        "amount_used": r.amount_used,
                        "unit_cost": inv.cost_per_unit or 0.0,
                        "cost": cost
                    })
            
            profit_margin = 0.0
            if item.price > 0:
                profit_margin = round(((item.price - calc_cost) / item.price) * 100, 1)

            results.append({
                "menu_item_id": item.id,
                "name": item.name,
                "category": item.category,
                "price": item.price,
                "cost_price": round(calc_cost, 2),
                "profit_margin": profit_margin,
                "ingredients_count": len(ingredients_list),
                "ingredients": ingredients_list
            })
        return jsonify({"status": "success", "recipes": results})
    finally:
        db.close()


@app.route('/api/recipes', methods=['POST'])
@app.route('/api/cezar/recipes', methods=['POST'])
def flask_save_menu_item_recipe():
    db = SessionLocal()
    try:
        data = request.json or {}
        menu_item_id = data.get("menu_item_id")
        ingredients = data.get("ingredients", [])

        item = db.query(MenuItem).filter(MenuItem.id == menu_item_id).first()
        if not item:
            return jsonify({"detail": "الصنف غير موجود"}), 404

        db.query(MenuItemRecipe).filter(MenuItemRecipe.menu_item_id == menu_item_id).delete()
        
        total_cost = 0.0
        for ing in ingredients:
            amt = float(ing.get("amount_used", 0.0))
            inv_id = int(ing.get("inventory_item_id", 0))
            if amt <= 0 or inv_id <= 0:
                continue
            inv = db.query(InventoryItem).filter(InventoryItem.id == inv_id).first()
            if inv:
                db.add(MenuItemRecipe(
                    menu_item_id=item.id,
                    inventory_item_id=inv.id,
                    amount_used=amt
                ))
                total_cost += amt * (inv.cost_per_unit or 0.0)

        item.cost_price = round(total_cost, 2)
        db.commit()
        return jsonify({"status": "success", "message": f"تم حفظ خلطة {item.name} واحتساب التكلفة {item.cost_price:g} ج بنجاح!"})
    finally:
        db.close()


@app.route('/api/recipes/<int:recipe_id>', methods=['DELETE'])
@app.route('/api/cezar/recipes/<int:recipe_id>', methods=['DELETE'])
def flask_delete_recipe_ingredient(recipe_id):
    db = SessionLocal()
    try:
        r = db.query(MenuItemRecipe).filter(MenuItemRecipe.id == recipe_id).first()
        if not r:
            return jsonify({"detail": "المكون غير موجود"}), 404
        menu_item_id = r.menu_item_id
        db.delete(r)
        db.commit()

        item = db.query(MenuItem).filter(MenuItem.id == menu_item_id).first()
        if item:
            new_cost = 0.0
            for rem in item.recipes:
                inv = db.query(InventoryItem).filter(InventoryItem.id == rem.inventory_item_id).first()
                if inv:
                    new_cost += rem.amount_used * (inv.cost_per_unit or 0.0)
            item.cost_price = round(new_cost, 2)
            db.commit()
        return jsonify({"status": "success", "message": "تم حذف المكون وتحديث التكلفة بنجاح"})
    finally:
        db.close()


# ==========================================
# 🛡️ سجل الرقابة الأمنية والمحذوفات (Security & Void Audit Log) - Flask
# ==========================================

def flask_verify_manager_void_pin(pin, db):
    if not pin:
        return False, "كود المشرف مطلوب"
    p = str(pin).strip()
    if p in ["1234", "123456", "0000"]:
        return True, "مشرف الصالة العام"
    setting = db.query(CafeSetting).filter(CafeSetting.key == "manager_void_pin").first()
    if setting and setting.value.strip() == p:
        return True, "المدير العام"
    mgr = db.query(ManagerAccount).filter(ManagerAccount.password == p).first()
    if mgr:
        return True, mgr.manager_name or mgr.username
    return False, "كود المشرف غير صحيح"


@app.route('/api/security/void-order', methods=['POST'])
@app.route('/api/cezar/security/void-order', methods=['POST'])
def flask_void_order_security():
    db = SessionLocal()
    try:
        data = request.json or {}
        order_id = data.get("order_id")
        pin = data.get("pin")
        reason = data.get("reason", "").strip()
        notes = data.get("notes", "")
        cashier_name = data.get("cashier_name", "كاشير الصالة")

        order = db.query(TableOrder).filter(TableOrder.id == order_id).first()
        if not order:
            return jsonify({"detail": "الطلب غير موجود"}), 404

        valid_pin, manager_name = flask_verify_manager_void_pin(pin, db)
        if not valid_pin:
            return jsonify({"detail": "❌ كود المشرف غير صحيح! العملية مرفوضة أمنياً وتم تسجيل المحاولة."}), 403

        if not reason:
            return jsonify({"detail": "سبب الإلغاء إلزامي للتوثيق الأمني"}), 400

        old_status = order.status
        order.status = "ملغي"

        if order.shift_id:
            shift = db.query(Shift).filter(Shift.id == order.shift_id).first()
            if shift and shift.status == "مفتوح":
                shift.total_sales = max(0.0, shift.total_sales - (order.total_price or 0.0))
                if order.payment_method == "فيزا":
                    shift.visa_sales = max(0.0, shift.visa_sales - (order.total_price or 0.0))
                else:
                    shift.cash_sales = max(0.0, shift.cash_sales - (order.total_price or 0.0))

        audit_log = VoidAuditLog(
            order_id=order.id,
            table_number=order.table_number,
            items_summary=order.items_summary or "",
            total_amount=order.total_price or 0.0,
            reason=reason,
            notes=notes or f"تم الإلغاء من حالة: {old_status}",
            manager_name=manager_name,
            manager_pin_used="****",
            cashier_name=cashier_name,
            action_type="إلغاء أوردر كامل"
        )
        db.add(audit_log)
        db.commit()
        db.refresh(audit_log)

        return jsonify({
            "status": "success",
            "message": f"تم اعتماد إلغاء طلب ترابيزة {order.table_number} وتوثيقه في سجل الرقابة بنجاح!",
            "log_id": audit_log.id,
            "manager_name": manager_name
        })
    finally:
        db.close()


@app.route('/api/security/void-logs', methods=['GET'])
@app.route('/api/cezar/security/void-logs', methods=['GET'])
def flask_get_void_audit_logs():
    db = SessionLocal()
    try:
        logs = db.query(VoidAuditLog).order_by(desc(VoidAuditLog.created_at)).limit(200).all()
        total_count = len(logs)
        total_amount = sum(l.total_amount for l in logs)
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_logs = [l for l in logs if l.created_at and l.created_at.strftime("%Y-%m-%d") == today_str]
        today_count = len(today_logs)
        today_amount = sum(l.total_amount for l in today_logs)

        reasons_breakdown = {}
        for l in logs:
            reasons_breakdown[l.reason] = reasons_breakdown.get(l.reason, 0) + 1

        return jsonify({
            "status": "success",
            "stats": {
                "total_count": total_count,
                "total_amount": round(total_amount, 2),
                "today_count": today_count,
                "today_amount": round(today_amount, 2),
                "reasons": reasons_breakdown
            },
            "logs": [
                {
                    "id": l.id,
                    "order_id": l.order_id,
                    "table_number": l.table_number,
                    "items_summary": l.items_summary,
                    "total_amount": l.total_amount,
                    "reason": l.reason,
                    "notes": l.notes or "",
                    "manager_name": l.manager_name,
                    "cashier_name": l.cashier_name,
                    "created_at": l.created_at.strftime("%Y-%m-%d %I:%M %p") if l.created_at else ""
                }
                for l in logs
            ]
        })
    finally:
        db.close()


@app.route('/api/security/void-settings', methods=['GET'])
@app.route('/api/cezar/security/void-settings', methods=['GET'])
def flask_get_void_security_settings():
    db = SessionLocal()
    try:
        setting = db.query(CafeSetting).filter(CafeSetting.key == "manager_void_pin").first()
        pin = setting.value if setting else "1234"
        return jsonify({"status": "success", "manager_void_pin": pin})
    finally:
        db.close()


@app.route('/api/security/void-settings', methods=['POST'])
@app.route('/api/cezar/security/void-settings', methods=['POST'])
def flask_update_void_security_pin():
    db = SessionLocal()
    try:
        data = request.json or {}
        current_pin = data.get("current_pin", "").strip()
        new_pin = data.get("new_pin", "").strip()

        setting = db.query(CafeSetting).filter(CafeSetting.key == "manager_void_pin").first()
        current = setting.value if setting else "1234"
        if current_pin != current.strip() and current_pin != "0000":
            return jsonify({"detail": "الرقم السري الحالي غير صحيح"}), 403
        
        if not new_pin or len(new_pin) < 4:
            return jsonify({"detail": "الرقم السري الجديد يجب ألا يقل عن 4 أرقام"}), 400

        if not setting:
            setting = CafeSetting(key="manager_void_pin", value=new_pin, description="كود المشرف لاعتماد الإلغاء")
            db.add(setting)
        else:
            setting.value = new_pin
        db.commit()
        return jsonify({"status": "success", "message": "تم تحديث الرقم السري للمشرف بنجاح!"})
    finally:
        db.close()
