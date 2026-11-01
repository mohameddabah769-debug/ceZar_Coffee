import os
import sys
import io
import json
import urllib.parse
from datetime import datetime

import qrcode
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from .database import engine, Base, SessionLocal
from .models import MenuItem, TableOrder, ManagerAccount
from .seed import seed_menu

# تهيئة الجداول وحساب المدير والمنيو تلقائياً
Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    seed_menu(db)
    if db.query(ManagerAccount).count() == 0:
        db.add(ManagerAccount(username="admin", password="123", manager_name="مدير سيزر كوفي"))
        db.commit()

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")


def json_response(start_response, status_code, data):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    status_str = f"{status_code} OK" if status_code == 200 else f"{status_code} Error"
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Access-Control-Allow-Origin", "*"),
        ("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"),
        ("Access-Control-Allow-Headers", "Content-Type"),
    ]
    start_response(status_str, headers)
    return [body]


def html_response(start_response, filename):
    file_path = os.path.join(TEMPLATES_DIR, filename)
    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            body = f.read()
    else:
        body = f"<h2>ملف {filename} غير موجود</h2>".encode("utf-8")
    headers = [
        ("Content-Type", "text/html; charset=utf-8"),
        ("Content-Length", str(len(body))),
    ]
    start_response("200 OK", headers)
    return [body]


def redirect_response(start_response, location):
    headers = [("Location", location), ("Content-Length", "0")]
    start_response("302 Found", headers)
    return [b""]


def application(environ, start_response):
    path = environ.get("PATH_INFO", "/").rstrip("/")
    if not path:
        path = "/"
    method = environ.get("REQUEST_METHOD", "GET").upper()
    query_string = environ.get("QUERY_STRING", "")
    params = urllib.parse.parse_qs(query_string)

    if method == "OPTIONS":
        headers = [
            ("Access-Control-Allow-Origin", "*"),
            ("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type"),
            ("Content-Length", "0"),
        ]
        start_response("200 OK", headers)
        return [b""]

    # قراءة بيانات POST / PUT JSON بأمان
    body_data = {}
    try:
        content_length = int(environ.get("CONTENT_LENGTH", 0) or 0)
        if content_length > 0:
            raw_body = environ["wsgi.input"].read(content_length)
            body_data = json.loads(raw_body.decode("utf-8"))
    except Exception:
        body_data = {}

    # 1. الصفحات الرئيسية
    if path == "/" and method == "GET":
        return redirect_response(start_response, "/admin")

    if path in ["/menu", "/cezar/menu"] and method == "GET":
        return html_response(start_response, "menu.html")

    if path in ["/admin", "/cezar/admin"] and method == "GET":
        return html_response(start_response, "admin.html")

    if path in ["/qr-cards", "/cezar/qr-generator"] and method == "GET":
        return html_response(start_response, "qr_cards.html")

    # 2. واجهات برمجة المنيو
    if path in ["/api/menu-items", "/api/cezar/menu-items"]:
        if method == "GET":
            all_items = params.get("all_items", ["false"])[0].lower() == "true"
            category = params.get("category", [None])[0]
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
                        "is_available": item.is_available,
                    })
                return json_response(start_response, 200, {"categories": grouped, "total_count": len(items)})

        elif method == "POST":
            new_item = MenuItem(
                name=str(body_data.get("name", "")).strip(),
                category=str(body_data.get("category", "")).strip(),
                price=float(body_data.get("price", 0)),
                description=body_data.get("description"),
                is_available=bool(body_data.get("is_available", True)),
            )
            with SessionLocal() as db:
                db.add(new_item)
                db.commit()
                db.refresh(new_item)
                return json_response(start_response, 200, {"status": "success", "item": {"id": new_item.id, "name": new_item.name}})

    # تعديل أو مسح صنف
    if (path.startswith("/api/menu-items/") or path.startswith("/api/cezar/menu-items/")):
        item_id = int(path.split("/")[-1])
        with SessionLocal() as db:
            item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
            if not item:
                return json_response(start_response, 404, {"detail": "Item not found"})
            if method == "PUT":
                if "name" in body_data and body_data["name"] is not None:
                    item.name = str(body_data["name"]).strip()
                if "category" in body_data and body_data["category"] is not None:
                    item.category = str(body_data["category"]).strip()
                if "price" in body_data and body_data["price"] is not None:
                    item.price = float(body_data["price"])
                if "description" in body_data:
                    item.description = body_data["description"]
                if "is_available" in body_data and body_data["is_available"] is not None:
                    item.is_available = bool(body_data["is_available"])
                db.commit()
                return json_response(start_response, 200, {"status": "success", "item": {"id": item.id, "name": item.name, "price": item.price, "is_available": item.is_available}})
            elif method == "DELETE":
                db.delete(item)
                db.commit()
                return json_response(start_response, 200, {"status": "success", "deleted_id": item_id})

    # 3. واجهات برمجة الطلبات
    if path in ["/api/orders", "/api/cezar/orders"]:
        if method == "POST":
            items = body_data.get("items", [])
            if not items:
                return json_response(start_response, 400, {"detail": "السلة فارغة"})
            lines = []
            total = 0.0
            for it in items:
                p = float(it.get("price", 0))
                q = int(it.get("quantity", 1))
                t = p * q
                total += t
                lines.append(f"- {q}x {it.get('name')}: {t:g} ج")
            summary = "\n".join(lines)
            tbl = int(body_data.get("table_number", 1))
            order = TableOrder(
                table_number=tbl,
                items_summary=summary,
                total_price=total,
                customer_name=body_data.get("customer_name") or f"ترابيزة {tbl}",
                customer_phone=body_data.get("customer_phone") or "",
                notes=body_data.get("notes") or "",
                status="جديد",
            )
            with SessionLocal() as db:
                db.add(order)
                db.commit()
                db.refresh(order)
                return json_response(start_response, 200, {
                    "status": "success",
                    "message": f"تم استلام طلب ترابيزة {order.table_number} بنجاح!",
                    "order_id": order.id,
                    "table_number": order.table_number,
                    "total_price": order.total_price,
                })
        elif method == "GET":
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
                    TableOrder.status != "نداء ويتر",
                ).scalar() or 0.0
                return json_response(start_response, 200, {
                    "stats": {
                        "total_orders": total_orders,
                        "total_sales": round(total_sales, 2),
                        "pending_orders": pending_count,
                        "delivered_orders": delivered_count,
                        "active_orders": pending_count,
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
                            "created_at": o.created_at.strftime("%I:%M %p") if o.created_at else "",
                        }
                        for o in orders
                    ],
                })

    # تغيير حالة طلب
    if (path.startswith("/api/orders/") or path.startswith("/api/cezar/orders/")) and path.endswith("/status") and method == "POST":
        parts = path.split("/")
        order_id = int(parts[-2])
        new_status = body_data.get("status")
        with SessionLocal() as db:
            order = db.query(TableOrder).filter(TableOrder.id == order_id).first()
            if not order:
                return json_response(start_response, 404, {"detail": "Order not found"})
            order.status = new_status
            if order.status in ["تم التقديم", "تمت التسوية"] and (order.items_summary and "طلب الحساب" in order.items_summary):
                db.query(TableOrder).filter(
                    TableOrder.table_number == order.table_number,
                    TableOrder.status.in_(["جديد", "جاري التحضير", "قيد التحضير"]),
                ).update({"status": "تم التقديم"}, synchronize_session=False)
            db.commit()
            return json_response(start_response, 200, {"status": "success", "order_id": order.id, "new_status": order.status})

    # نداء الويتر
    if path in ["/api/orders/call-waiter", "/api/cezar/orders/call-waiter"] and method == "POST":
        tbl = int(body_data.get("table_number", 1))
        order = TableOrder(
            table_number=tbl,
            items_summary="🔔 نداء الويتر (طلب مساعدة / استفسار)",
            total_price=0.0,
            customer_name=f"ترابيزة {tbl}",
            status="نداء ويتر",
        )
        with SessionLocal() as db:
            db.add(order)
            db.commit()
            db.refresh(order)
            return json_response(start_response, 200, {"status": "success", "message": f"تم إرسال نداء الويتر لترابيزة {tbl} فوراً!"})

    # طلب الحساب
    if path in ["/api/orders/request-bill", "/api/cezar/orders/request-bill"] and method == "POST":
        tbl = int(body_data.get("table_number", 1))
        method_name = body_data.get("payment_method", "كاش")
        if method_name not in ["كاش", "فيزا"]:
            method_name = "كاش"
        icon = "💵" if method_name == "كاش" else "💳"
        with SessionLocal() as db:
            active_orders = db.query(TableOrder).filter(
                TableOrder.table_number == tbl,
                TableOrder.status != "ملغي",
                ~TableOrder.status.like("طلب حساب%"),
                TableOrder.status != "نداء ويتر",
                ~TableOrder.items_summary.like("%طلب الحساب%"),
                ~TableOrder.items_summary.like("%نداء الويتر%"),
                TableOrder.total_price > 0,
            ).all()
            total_bill = sum(o.total_price for o in active_orders)
            if active_orders:
                orders_details = [o.items_summary for o in active_orders]
                items_text = "\n".join(orders_details)
                summary = f"🧾 طلب الحساب النهائي ({method_name}) {icon}\n💰 الإجمالي المطلوب تحصيله: {total_bill:g} جنيه\n📋 الطلبات:\n{items_text}"
            else:
                summary = f"🧾 طلب الحساب النهائي ({method_name}) {icon} (طلب حساب مباشر بدون أوردرات مسبقة)"
            order = TableOrder(
                table_number=tbl,
                items_summary=summary,
                total_price=total_bill,
                customer_name=f"ترابيزة {tbl}",
                status=f"طلب حساب ({method_name})",
            )
            db.add(order)
            db.commit()
            db.refresh(order)
            return json_response(start_response, 200, {
                "status": "success",
                "message": f"تم إرسال طلب الحساب لترابيزة {tbl} بنجاح! الإجمالي: {total_bill:g} جنيه ({method_name})",
                "order_id": order.id,
                "total_bill": total_bill,
            })

    # كشف حساب ترابيزة
    if (path.startswith("/api/tables/") or path.startswith("/api/cezar/tables/")) and path.endswith("/bill") and method == "GET":
        parts = path.split("/")
        tbl = int(parts[-2])
        with SessionLocal() as db:
            active_orders = db.query(TableOrder).filter(
                TableOrder.table_number == tbl,
                TableOrder.status != "ملغي",
                ~TableOrder.status.like("طلب حساب%"),
                TableOrder.status != "نداء ويتر",
                ~TableOrder.items_summary.like("%طلب الحساب%"),
                ~TableOrder.items_summary.like("%نداء الويتر%"),
                TableOrder.total_price > 0,
            ).all()
            total_bill = sum(o.total_price for o in active_orders)
            orders_list = [
                {
                    "id": o.id,
                    "items_summary": o.items_summary,
                    "total_price": o.total_price,
                    "status": o.status,
                    "notes": o.notes or "",
                    "created_at": o.created_at.strftime("%I:%M %p") if o.created_at else "",
                }
                for o in active_orders
            ]
            return json_response(start_response, 200, {
                "table_number": tbl,
                "total_bill": round(total_bill, 2),
                "orders_count": len(active_orders),
                "orders": orders_list,
            })

    # تتبع طلبات ترابيزة
    if (path.startswith("/api/tables/") or path.startswith("/api/cezar/tables/")) and path.endswith("/track") and method == "GET":
        parts = path.split("/")
        tbl = int(parts[-2])
        with SessionLocal() as db:
            orders = db.query(TableOrder).filter(
                TableOrder.table_number == tbl,
                ~TableOrder.items_summary.like("%طلب الحساب%"),
                ~TableOrder.items_summary.like("%نداء الويتر%"),
                TableOrder.total_price > 0,
            ).order_by(desc(TableOrder.id)).limit(25).all()

            orders_list = [
                {
                    "id": o.id,
                    "items_summary": o.items_summary,
                    "total_price": o.total_price,
                    "status": o.status,
                    "notes": o.notes or "",
                    "created_at": o.created_at.strftime("%I:%M %p") if o.created_at else "",
                }
                for o in orders
            ]
            active_count = sum(1 for o in orders if o.status in ["جديد", "جاري التحضير", "قيد التحضير"])

            return json_response(start_response, 200, {
                "status": "success",
                "table_number": tbl,
                "orders_count": len(orders_list),
                "active_count": active_count,
                "orders": orders_list,
            })

    # تتبع طلب برقم ID
    if (path.startswith("/api/orders/") or path.startswith("/api/cezar/orders/")) and not path.endswith("/status") and not path.endswith("/clear-all") and not path.endswith("/call-waiter") and not path.endswith("/request-bill") and method == "GET":
        try:
            order_id = int(path.split("/")[-1])
            with SessionLocal() as db:
                order = db.query(TableOrder).filter(TableOrder.id == order_id).first()
                if not order:
                    return json_response(start_response, 404, {"status": "error", "detail": "الطلب غير موجود"})
                return json_response(start_response, 200, {
                    "status": "success",
                    "id": order.id,
                    "table_number": order.table_number,
                    "items_summary": order.items_summary,
                    "total_price": order.total_price,
                    "status": order.status,
                    "notes": order.notes or "",
                    "created_at": order.created_at.strftime("%I:%M %p") if order.created_at else "",
                })
        except Exception:
            pass

    # تصفير الطلبات
    if path in ["/api/orders/clear-all", "/api/cezar/orders/clear-all"] and method == "POST":
        with SessionLocal() as db:
            db.query(TableOrder).delete()
            db.commit()
            return json_response(start_response, 200, {"status": "success", "message": "تم تصفير جميع الطلبات وبدء وردية جديدة بنجاح!"})

    # توليد كود الـ QR
    if path.startswith("/api/qr/") or path.startswith("/api/cezar/qr/"):
        tbl = int(path.split("/")[-1])
        host = params.get("host", [""])[0]
        if host and host.strip():
            clean_host = host.strip().rstrip("/")
            if not clean_host.startswith("http://") and not clean_host.startswith("https://"):
                clean_host = f"http://{clean_host}"
            target_url = f"{clean_host}/menu?table={tbl}"
        else:
            host_header = environ.get("HTTP_HOST", "Deboo.pythonanywhere.com")
            target_url = f"https://{host_header}/menu?table={tbl}"

        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
        qr.add_data(target_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#2B1810", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        body = buf.getvalue()
        headers = [("Content-Type", "image/png"), ("Content-Length", str(len(body)))]
        start_response("200 OK", headers)
        return [body]

    # تسجيل الدخول وتغيير البيانات
    if path in ["/api/auth/login", "/api/cezar/auth/login"] and method == "POST":
        u = str(body_data.get("username", "")).strip()
        p = str(body_data.get("password", "")).strip()
        with SessionLocal() as db:
            account = db.query(ManagerAccount).filter(ManagerAccount.username == u, ManagerAccount.password == p).first()
            if not account:
                return json_response(start_response, 401, {"detail": "اسم المستخدم أو كلمة المرور غير صحيحة"})
            return json_response(start_response, 200, {"status": "success", "username": account.username, "manager_name": account.manager_name or "المدير العام"})

    if path in ["/api/auth/change-credentials", "/api/cezar/auth/change-credentials"] and method == "POST":
        curr = str(body_data.get("current_password", "")).strip()
        new_user = str(body_data.get("new_username", "")).strip()
        new_pass = str(body_data.get("new_password", "")).strip()
        with SessionLocal() as db:
            account = db.query(ManagerAccount).filter(ManagerAccount.password == curr).first()
            if not account:
                return json_response(start_response, 400, {"detail": "كلمة المرور الحالية غير صحيحة!"})
            if not new_user or not new_pass:
                return json_response(start_response, 400, {"detail": "اسم المستخدم وكلمة المرور الجديدة لا يمكن أن تكون فارغة!"})
            account.username = new_user
            account.password = new_pass
            db.commit()
            return json_response(start_response, 200, {"status": "success", "message": "تم تحديث بيانات الدخول بنجاح!", "username": account.username})

    # صفحة غير موجودة 404
    return json_response(start_response, 404, {"detail": "Not Found"})
