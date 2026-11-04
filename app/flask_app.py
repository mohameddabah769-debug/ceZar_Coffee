import os
import sys
import io
import qrcode
from datetime import datetime
from flask import Flask, request, jsonify, redirect, Response
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, text

from .database import engine, Base, SessionLocal
from .models import MenuItem, TableOrder, ManagerAccount, Shift, Expense, Reservation, WaitingList
from .seed import seed_menu

# تهيئة الجداول تلقائياً
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
        ]
        for col_name, col_type in columns_to_add:
            try:
                conn.execute(text(f"ALTER TABLE table_orders ADD COLUMN {col_name} {col_type}"))
                conn.commit()
            except Exception:
                pass

auto_migrate_columns()

with SessionLocal() as db:
    seed_menu(db)
    if db.query(ManagerAccount).filter(ManagerAccount.username == "admin").count() == 0:
        db.add(ManagerAccount(username="admin", password="123", manager_name="مدير سيزر كوفي"))
    if db.query(ManagerAccount).filter(ManagerAccount.username == "cezar").count() == 0:
        db.add(ManagerAccount(username="cezar", password="0000", manager_name="كافيه سيزر"))
    db.commit()

app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
    static_url_path="/static"
)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")


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


@app.route("/qr-cards")
@app.route("/cezar/qr-generator")
def get_qr_cards_page():
    file_path = os.path.join(TEMPLATES_DIR, "qr_cards.html")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return Response(f.read(), mimetype="text/html; charset=utf-8")
    return Response("<h2>جاري تحميل كروت الـ QR للترابيزات...</h2>", mimetype="text/html; charset=utf-8")


# ==========================================
# 2. واجهات برمجة الأصناف (Menu APIs)
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


@app.route("/api/menu-items/<int:item_id>", methods=["PUT"])
@app.route("/api/cezar/menu-items/<int:item_id>", methods=["PUT"])
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


@app.route("/api/menu-items/<int:item_id>", methods=["DELETE"])
@app.route("/api/cezar/menu-items/<int:item_id>", methods=["DELETE"])
def delete_menu_item(item_id):
    with SessionLocal() as db:
        item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
        if not item:
            return jsonify({"detail": "Item not found"}), 404
        db.delete(item)
        db.commit()
        return jsonify({"status": "success", "deleted_id": item_id})


# ==========================================
# 3. واجهات برمجة الطلبات والكاشير (POS & Orders)
# ==========================================

@app.route("/api/orders", methods=["POST"])
@app.route("/api/cezar/orders", methods=["POST"])
def create_table_order():
    data = request.json or {}
    items = data.get("items") or []
    table_num = int(data.get("table_number") or 1)
    if not items:
        return jsonify({"detail": "السلة فارغة"}), 400

    lines = []
    total = 0.0
    for item in items:
        p = float(item.get("price") or 0.0)
        q = int(item.get("quantity") or 1)
        sub = p * q
        total += sub
        lines.append(f"- {q}x {item.get('name')}: {sub:g} ج")

    items_summary = "\n".join(lines)

    with SessionLocal() as db:
        current_shift = db.query(Shift).filter(Shift.status == "مفتوح").first()
        shift_id = current_shift.id if current_shift else None

        order = TableOrder(
            table_number=table_num,
            order_type="صالة",
            items_summary=items_summary,
            total_price=total,
            customer_name=data.get("customer_name") or f"ترابيزة {table_num}",
            customer_phone=data.get("customer_phone") or "",
            notes=data.get("notes") or "",
            status="جديد",
            payment_method="كاش",
            shift_id=shift_id
        )
        db.add(order)
        if current_shift:
            current_shift.total_sales += total
            current_shift.cash_sales += total
        db.commit()
        db.refresh(order)
        return jsonify({
            "status": "success",
            "message": f"تم استلام طلب ترابيزة {order.table_number} بنجاح!",
            "order_id": order.id,
            "table_number": order.table_number,
            "total_price": order.total_price
        })


@app.route("/api/pos/orders", methods=["POST"])
@app.route("/api/cezar/pos/orders", methods=["POST"])
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
        lines.append(f"- {q}x {item.get('name')}: {sub:g} ج")

    delivery_fee = float(data.get("delivery_fee") or 0.0) if order_type == "دليفري" else 0.0
    grand_total = items_total + delivery_fee
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
def get_table_bill(table_number):
    with SessionLocal() as db:
        active_orders = db.query(TableOrder).filter(
            TableOrder.table_number == table_number,
            TableOrder.status != "ملغي",
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



@app.route("/api/tables/<int:table_number>/track", methods=["GET"])
@app.route("/api/cezar/tables/<int:table_number>/track", methods=["GET"])
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
def request_bill_endpoint():
    data = request.json or {}
    table_num = int(data.get("table_number") or 1)
    method = data.get("payment_method") or "كاش"
    icon = "💵" if method == "كاش" else "💳"

    with SessionLocal() as db:
        active_orders = db.query(TableOrder).filter(
            TableOrder.table_number == table_num,
            TableOrder.status != "ملغي",
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
# 4. واجهات إدارة الشيفتات والمصروفات (Shifts & Expenses)
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
# 5. واجهات خدمة الحجوزات (Reservations APIs)
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


# ==========================================
# 6. واجهات خدمة قائمة الانتظار (Waiting List APIs)
# ==========================================

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
# 7. نظام تسجيل الدخول
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
            "manager_name": account.manager_name or "المدير العام"
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
