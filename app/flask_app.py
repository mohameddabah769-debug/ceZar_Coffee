import os
import sys
import io
import qrcode
from flask import Flask, request, jsonify, redirect, Response
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from .database import engine, Base, SessionLocal
from .models import MenuItem, TableOrder, ManagerAccount
from .seed import seed_menu

# تهيئة الجداول وحساب المدير والمنيو تلقائياً
Base.metadata.create_all(bind=engine)
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
    data = request.get_json(silent=True) or {}
    new_item = MenuItem(
        name=str(data.get("name", "")).strip(),
        category=str(data.get("category", "")).strip(),
        price=float(data.get("price", 0)),
        description=data.get("description"),
        is_available=bool(data.get("is_available", True))
    )
    with SessionLocal() as db:
        db.add(new_item)
        db.commit()
        db.refresh(new_item)
        return jsonify({"status": "success", "item": {"id": new_item.id, "name": new_item.name}})


@app.route("/api/menu-items/<int:item_id>", methods=["PUT"])
@app.route("/api/cezar/menu-items/<int:item_id>", methods=["PUT"])
def update_menu_item(item_id):
    data = request.get_json(silent=True) or {}
    with SessionLocal() as db:
        item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
        if not item:
            return jsonify({"detail": "Item not found"}), 404

        if "name" in data and data["name"] is not None:
            item.name = str(data["name"]).strip()
        if "category" in data and data["category"] is not None:
            item.category = str(data["category"]).strip()
        if "price" in data and data["price"] is not None:
            item.price = float(data["price"])
        if "description" in data:
            item.description = data["description"]
        if "is_available" in data and data["is_available"] is not None:
            item.is_available = bool(data["is_available"])

        db.commit()
        db.refresh(item)
        return jsonify({
            "status": "success",
            "item": {
                "id": item.id,
                "name": item.name,
                "price": item.price,
                "is_available": item.is_available
            }
        })


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
# 3. واجهات برمجة الطلبات (Order APIs)
# ==========================================

@app.route("/api/orders", methods=["POST"])
@app.route("/api/cezar/orders", methods=["POST"])
def create_table_order():
    data = request.get_json(silent=True) or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"detail": "السلة فارغة"}), 400

    lines = []
    total = 0.0
    for item in items:
        item_price = float(item.get("price", 0))
        item_qty = int(item.get("quantity", 1))
        item_total = item_price * item_qty
        total += item_total
        lines.append(f"- {item_qty}x {item.get('name')}: {item_total:g} ج")

    items_summary = "\n".join(lines)
    tbl = int(data.get("table_number", 1))

    order = TableOrder(
        table_number=tbl,
        items_summary=items_summary,
        total_price=total,
        customer_name=data.get("customer_name") or f"ترابيزة {tbl}",
        customer_phone=data.get("customer_phone") or "",
        notes=data.get("notes") or "",
        status="جديد"
    )
    with SessionLocal() as db:
        db.add(order)
        db.commit()
        db.refresh(order)
        return jsonify({
            "status": "success",
            "message": f"تم استلام طلب ترابيزة {order.table_number} بنجاح!",
            "order_id": order.id,
            "table_number": order.table_number,
            "total_price": order.total_price
        })


@app.route("/api/orders", methods=["GET"])
@app.route("/api/cezar/orders", methods=["GET"])
def get_orders():
    with SessionLocal() as db:
        orders = db.query(TableOrder).order_by(desc(TableOrder.created_at)).limit(100).all()
        total_orders = db.query(TableOrder).count()
        delivered_count = db.query(TableOrder).filter(TableOrder.status.in_(["تم التقديم", "تمت التسوية"])).count()
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
                    "table_number": o.table_number,
                    "items_summary": o.items_summary,
                    "total_price": o.total_price,
                    "status": o.status,
                    "customer_name": o.customer_name,
                    "customer_phone": o.customer_phone,
                    "notes": o.notes,
                    "created_at": o.created_at.strftime("%I:%M %p") if o.created_at else ""
                }
                for o in orders
            ]
        })


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
        orders_list = [
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

        return jsonify({
            "table_number": table_number,
            "total_bill": round(total_bill, 2),
            "orders_count": len(active_orders),
            "orders": orders_list
        })


@app.route("/api/tables/<int:table_number>/track", methods=["GET"])
@app.route("/api/cezar/tables/<int:table_number>/track", methods=["GET"])
def track_table_orders(table_number):
    with SessionLocal() as db:
        orders = db.query(TableOrder).filter(
            TableOrder.table_number == table_number,
            ~TableOrder.items_summary.like("%طلب الحساب%"),
            ~TableOrder.items_summary.like("%نداء الويتر%"),
            TableOrder.total_price > 0
        ).order_by(TableOrder.id.desc()).limit(25).all()

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
            return jsonify({"status": "error", "detail": "الطلب غير موجود"}), 404
        return jsonify({
            "status": "success",
            "id": order.id,
            "table_number": order.table_number,
            "items_summary": order.items_summary,
            "total_price": order.total_price,
            "status": order.status,
            "notes": order.notes or "",
            "created_at": order.created_at.strftime("%I:%M %p") if order.created_at else ""
        })


@app.route("/api/orders/<int:order_id>/status", methods=["POST"])
@app.route("/api/cezar/orders/<int:order_id>/status", methods=["POST"])
def update_order_status(order_id):
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    with SessionLocal() as db:
        order = db.query(TableOrder).filter(TableOrder.id == order_id).first()
        if not order:
            return jsonify({"detail": "Order not found"}), 404

        order.status = new_status
        if order.status in ["تم التقديم", "تمت التسوية"] and (order.items_summary and "طلب الحساب" in order.items_summary):
            db.query(TableOrder).filter(
                TableOrder.table_number == order.table_number,
                TableOrder.status.in_(["جديد", "جاري التحضير", "قيد التحضير"])
            ).update({"status": "تم التقديم"}, synchronize_session=False)

        db.commit()
        return jsonify({"status": "success", "order_id": order.id, "new_status": order.status})


@app.route("/api/orders/call-waiter", methods=["POST"])
@app.route("/api/cezar/orders/call-waiter", methods=["POST"])
def call_waiter_endpoint():
    data = request.get_json(silent=True) or {}
    tbl = int(data.get("table_number", 1))
    order = TableOrder(
        table_number=tbl,
        items_summary="🔔 نداء الويتر (طلب مساعدة / استفسار)",
        total_price=0.0,
        customer_name=f"ترابيزة {tbl}",
        status="نداء ويتر"
    )
    with SessionLocal() as db:
        db.add(order)
        db.commit()
        db.refresh(order)
        return jsonify({"status": "success", "message": f"تم إرسال نداء الويتر لترابيزة {tbl} فوراً!"})


@app.route("/api/orders/request-bill", methods=["POST"])
@app.route("/api/cezar/orders/request-bill", methods=["POST"])
def request_bill_endpoint():
    data = request.get_json(silent=True) or {}
    tbl = int(data.get("table_number", 1))
    method = data.get("payment_method", "كاش")
    if method not in ["كاش", "فيزا"]:
        method = "كاش"
    icon = "💵" if method == "كاش" else "💳"

    with SessionLocal() as db:
        active_orders = db.query(TableOrder).filter(
            TableOrder.table_number == tbl,
            TableOrder.status != "ملغي",
            ~TableOrder.status.like("طلب حساب%"),
            TableOrder.status != "نداء ويتر",
            ~TableOrder.items_summary.like("%طلب الحساب%"),
            ~TableOrder.items_summary.like("%نداء الويتر%"),
            TableOrder.total_price > 0
        ).all()

        total_bill = sum(o.total_price for o in active_orders)
        if active_orders:
            orders_details = [o.items_summary for o in active_orders]
            items_text = "\n".join(orders_details)
            summary = f"🧾 طلب الحساب النهائي ({method}) {icon}\n💰 الإجمالي المطلوب تحصيله: {total_bill:g} جنيه\n📋 الطلبات:\n{items_text}"
        else:
            summary = f"🧾 طلب الحساب النهائي ({method}) {icon} (طلب حساب مباشر بدون أوردرات مسبقة)"

        order = TableOrder(
            table_number=tbl,
            items_summary=summary,
            total_price=total_bill,
            customer_name=f"ترابيزة {tbl}",
            status=f"طلب حساب ({method})"
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        return jsonify({
            "status": "success",
            "message": f"تم إرسال طلب الحساب لترابيزة {tbl} بنجاح! الإجمالي: {total_bill:g} جنيه ({method})",
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
# 4. توليد باركود QR عالي الدقة لأي ترابيزة
# ==========================================

@app.route("/api/qr/<int:table_number>", methods=["GET"])
@app.route("/api/cezar/qr/<int:table_number>", methods=["GET"])
def generate_table_qr(table_number):
    host = request.args.get("host")
    if host and host.strip():
        clean_host = host.strip().rstrip("/")
        if not clean_host.startswith("http://") and not clean_host.startswith("https://"):
            clean_host = f"http://{clean_host}"
        target_url = f"{clean_host}/menu?table={table_number}"
    else:
        target_url = f"{request.host_url.rstrip('/')}/menu?table={table_number}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(target_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#2B1810", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Response(buf.getvalue(), mimetype="image/png")


# ==========================================
# 5. نظام تسجيل دخول المدير وتغيير البيانات
# ==========================================

@app.route("/api/auth/login", methods=["POST"])
@app.route("/api/cezar/auth/login", methods=["POST"])
def manager_login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", "")).strip()

    with SessionLocal() as db:
        account = db.query(ManagerAccount).filter(
            ManagerAccount.username == username,
            ManagerAccount.password == password
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
    data = request.get_json(silent=True) or {}
    curr = str(data.get("current_password", "")).strip()
    new_user = str(data.get("new_username", "")).strip()
    new_pass = str(data.get("new_password", "")).strip()

    with SessionLocal() as db:
        account = db.query(ManagerAccount).filter(ManagerAccount.password == curr).first()
        if not account:
            return jsonify({"detail": "كلمة المرور الحالية غير صحيحة!"}), 400
        if not new_user or not new_pass:
            return jsonify({"detail": "اسم المستخدم وكلمة المرور الجديدة لا يمكن أن تكون فارغة!"}), 400

        account.username = new_user
        account.password = new_pass
        db.commit()
        return jsonify({
            "status": "success",
            "message": "تم تحديث بيانات الدخول بنجاح!",
            "username": account.username
        })
