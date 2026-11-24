# -*- coding: utf-8 -*-
"""
ceZar Coffee - Dedicated Arabic Excel Export Engine
محرك تصدير الإكسل الاحترافي باللغة العربية لكافيه سيزر
Generates formatted, styled, multi-sheet .xlsx workbooks using openpyxl with full RTL support.
"""

import io
from datetime import datetime, timedelta
from sqlalchemy import desc, func

from app.models import (
    MenuItem,
    InventoryItem,
    TableOrder,
    Expense,
    Employee,
    Shift,
    Supplier,
    CafeSetting
)

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False


def _get_styles():
    """Styles definition matching ceZar Coffee branding."""
    espresso_fill = PatternFill(start_color="2B1810", end_color="2B1810", fill_type="solid")
    gold_fill = PatternFill(start_color="C5A880", end_color="C5A880", fill_type="solid")
    orange_fill = PatternFill(start_color="D97706", end_color="D97706", fill_type="solid")
    zebra_fill = PatternFill(start_color="FAF7F2", end_color="FAF7F2", fill_type="solid")
    white_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
    total_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
    kpi_card_fill = PatternFill(start_color="F5F3EF", end_color="F5F3EF", fill_type="solid")

    font_title = Font(name="Arial", size=15, bold=True, color="2B1810")
    font_subtitle = Font(name="Arial", size=10, bold=False, color="6B7280")
    font_header = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    font_data = Font(name="Arial", size=10, bold=False, color="1F2937")
    font_bold = Font(name="Arial", size=10, bold=True, color="1F2937")
    font_total = Font(name="Arial", size=11, bold=True, color="92400E")

    thin_border_side = Side(style="thin", color="E5E7EB")
    cell_border = Border(
        left=thin_border_side,
        right=thin_border_side,
        top=thin_border_side,
        bottom=thin_border_side
    )
    header_border_side = Side(style="medium", color="C5A880")
    header_border = Border(
        left=thin_border_side,
        right=thin_border_side,
        top=thin_border_side,
        bottom=header_border_side
    )

    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    align_right = Alignment(horizontal="right", vertical="center", wrap_text=True)
    align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)

    return {
        "espresso_fill": espresso_fill,
        "gold_fill": gold_fill,
        "orange_fill": orange_fill,
        "zebra_fill": zebra_fill,
        "white_fill": white_fill,
        "total_fill": total_fill,
        "kpi_card_fill": kpi_card_fill,
        "font_title": font_title,
        "font_subtitle": font_subtitle,
        "font_header": font_header,
        "font_data": font_data,
        "font_bold": font_bold,
        "font_total": font_total,
        "cell_border": cell_border,
        "header_border": header_border,
        "align_center": align_center,
        "align_right": align_right,
        "align_left": align_left,
    }


def _setup_worksheet(ws, title, subtitle, headers, styles):
    """Sets up sheet RTL, branding title block, and header row."""
    # 1. Enable RTL
    ws.views.sheetView[0].rightToLeft = True

    # 2. Title Block
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    title_cell = ws.cell(row=1, column=1, value=title)
    title_cell.font = styles["font_title"]
    title_cell.alignment = styles["align_center"]
    ws.row_dimensions[1].height = 28

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(headers))
    sub_cell = ws.cell(row=2, column=1, value=f"{subtitle} | تاريخ الاستخراج: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}")
    sub_cell.font = styles["font_subtitle"]
    sub_cell.alignment = styles["align_center"]
    ws.row_dimensions[2].height = 18

    # 3. Headers
    ws.row_dimensions[4].height = 26
    for col_idx, h in enumerate(headers, start=1):
        c = ws.cell(row=4, column=col_idx, value=h)
        c.font = styles["font_header"]
        c.fill = styles["espresso_fill"]
        c.border = styles["header_border"]
        c.alignment = styles["align_center"]


def _auto_adjust_columns(ws, min_width=12, max_width=45):
    """Adjusts column widths dynamically based on content length with Arabic padding."""
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            # Skip merged title rows
            if cell.row in [1, 2]:
                continue
            val_str = str(cell.value or "")
            if val_str:
                max_len = max(max_len, len(val_str))
        ws.column_dimensions[col_letter].width = max(min(max_len + 4, max_width), min_width)


def generate_full_system_excel(db) -> io.BytesIO:
    """
    Generates a full 8-sheet Arabic Excel workbook encompassing the entire ceZar Coffee system.
    """
    if not OPENPYXL_AVAILABLE:
        raise ImportError("openpyxl is required to generate Excel files. Install via pip install openpyxl.")

    wb = Workbook()
    styles = _get_styles()

    # ==========================================
    # Sheet 1: 📊 الملخص العام والمؤشرات (Summary KPIs)
    # ==========================================
    ws_kpi = wb.active
    ws_kpi.title = "المؤشرات العامة"
    ws_kpi.views.sheetView[0].rightToLeft = True

    # Calculate system totals
    total_sales_val = db.query(func.coalesce(func.sum(TableOrder.total_price), 0.0)).filter(
        TableOrder.status != "ملغي",
        ~TableOrder.status.like("طلب حساب%"),
        TableOrder.status != "نداء ويتر"
    ).scalar() or 0.0

    total_orders_cnt = db.query(func.count(TableOrder.id)).filter(
        TableOrder.status != "ملغي",
        ~TableOrder.status.like("طلب حساب%"),
        TableOrder.status != "نداء ويتر",
        TableOrder.total_price > 0
    ).scalar() or 0

    total_expenses_val = db.query(func.coalesce(func.sum(Expense.amount), 0.0)).scalar() or 0.0
    net_operating_profit = total_sales_val - total_expenses_val
    avg_ticket = (total_sales_val / total_orders_cnt) if total_orders_cnt > 0 else 0.0

    menu_items_cnt = db.query(func.count(MenuItem.id)).filter(MenuItem.is_available == True).scalar() or 0
    inv_items = db.query(InventoryItem).all()
    total_inv_value = sum((getattr(i, 'current_stock', 0.0) or 0.0) * (getattr(i, 'cost_per_unit', 0.0) or 0.0) for i in inv_items)
    staff_cnt = db.query(func.count(Employee.id)).filter(Employee.status == "نشط").scalar() or 0
    closed_shifts_cnt = db.query(func.count(Shift.id)).filter(Shift.status == "مغلقة").scalar() or 0

    # Title Block
    ws_kpi.merge_cells("A1:D1")
    t1 = ws_kpi.cell(row=1, column=1, value="كافيه سيزر | ceZar COFFEE - لوحة القيادة والتقرير المالي الشامل")
    t1.font = styles["font_title"]
    t1.alignment = styles["align_center"]
    ws_kpi.row_dimensions[1].height = 32

    ws_kpi.merge_cells("A2:D2")
    t2 = ws_kpi.cell(row=2, column=1, value=f"تقرير شامل ومفصل مستخرج من قاعدة البيانات بتاريخ: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}")
    t2.font = styles["font_subtitle"]
    t2.alignment = styles["align_center"]
    ws_kpi.row_dimensions[2].height = 20

    # KPI Table Header
    headers_kpi = ["المؤشر المالي والتشغيلي", "القيمة", "الوحدة", "ملاحظات وتفاصيل"]
    ws_kpi.row_dimensions[4].height = 26
    for c_idx, h in enumerate(headers_kpi, start=1):
        cell = ws_kpi.cell(row=4, column=c_idx, value=h)
        cell.font = styles["font_header"]
        cell.fill = styles["espresso_fill"]
        cell.border = styles["header_border"]
        cell.alignment = styles["align_center"]

    kpi_rows = [
        ("إجمالي مبيعات النظام التاريخية", total_sales_val, "جنيه مصري", "تشمل الصالة والتيك أواي والدليفري المسددة"),
        ("إجمالي المصروفات والنثريات", total_expenses_val, "جنيه مصري", "المصروفات التشغيلية والمشتريات المسجلة"),
        ("صافي الربح التشغيلي التقديري", net_operating_profit, "جنيه مصري", "المبيعات الإجمالية ناقص المصروفات"),
        ("إجمالي عدد الفواتير والطلبات", total_orders_cnt, "طلب / فاتورة", "الطلبات المكتملة والمحاسب عليها"),
        ("متوسط قيمة الفاتورة (AOV)", avg_ticket, "جنيه مصري", "متوسط إنفاق العميل للطلب الواحد"),
        ("إجمالي القيمة التقديرية للمخزون", total_inv_value, "جنيه مصري", "حاصل ضرب الكميات المتاحة في سعر التكلفة"),
        ("عدد الأصناف المتاحة بالمنيو", menu_items_cnt, "صنف نشط", "الأصناف المعروضة للبيع حالياً"),
        ("عدد الموظفين النشطين", staff_cnt, "موظف", "الكاشيرات والباريستا والويترية"),
        ("عدد الورديات المغلقة المؤرشفة", closed_shifts_cnt, "وردية", "الورديات التي تمت مراجعتها وإقفال كاشيرها")
    ]

    for idx, (k_name, k_val, k_unit, k_note) in enumerate(kpi_rows, start=5):
        ws_kpi.row_dimensions[idx].height = 22
        fill = styles["zebra_fill"] if idx % 2 == 0 else styles["white_fill"]
        
        c1 = ws_kpi.cell(row=idx, column=1, value=k_name)
        c2 = ws_kpi.cell(row=idx, column=2, value=k_val)
        c3 = ws_kpi.cell(row=idx, column=3, value=k_unit)
        c4 = ws_kpi.cell(row=idx, column=4, value=k_note)

        for c in [c1, c2, c3, c4]:
            c.fill = fill
            c.border = styles["cell_border"]
            c.font = styles["font_data"]
            c.alignment = styles["align_center"]

        c1.alignment = styles["align_right"]
        c1.font = styles["font_bold"]
        c4.alignment = styles["align_right"]

        if isinstance(k_val, float):
            c2.number_format = '#,##0.00 "ج"'
            c2.font = styles["font_bold"]

    _auto_adjust_columns(ws_kpi)

    # ==========================================
    # Sheet 2: ☕ قائمة المنيو والأسعار (Menu)
    # ==========================================
    ws_menu = wb.create_sheet(title="قائمة المنيو")
    menu_headers = ["كود الصنف", "اسم الصنف", "القسم / التصنيف", "سعر البيع (ج)", "سعر التكلفة (ج)", "هامش الربح (ج)", "نسبة الربح %", "الحالة"]
    _setup_worksheet(ws_menu, "قائمة أصناف المنيو وأسعار البيع والتكلفة", "كافيه سيزر | ceZar Coffee", menu_headers, styles)

    menu_items = db.query(MenuItem).order_by(MenuItem.category, MenuItem.name).all()
    for row_idx, item in enumerate(menu_items, start=5):
        ws_menu.row_dimensions[row_idx].height = 20
        fill = styles["zebra_fill"] if row_idx % 2 == 0 else styles["white_fill"]

        cost = item.cost_price or 0.0
        price = item.price or 0.0
        margin = price - cost
        margin_pct = (margin / cost * 100) if cost > 0 else (100.0 if price > 0 else 0.0)

        data = [
            item.id,
            item.name,
            item.category,
            price,
            cost,
            margin,
            f"{margin_pct:.1f}%",
            "متاح للبيع" if item.is_available else "غير متاح (مخفي)"
        ]

        for col_idx, val in enumerate(data, start=1):
            cell = ws_menu.cell(row=row_idx, column=col_idx, value=val)
            cell.fill = fill
            cell.border = styles["cell_border"]
            cell.font = styles["font_data"]
            cell.alignment = styles["align_center"]

            if col_idx == 2:  # Name
                cell.alignment = styles["align_right"]
                cell.font = styles["font_bold"]
            elif col_idx in [4, 5, 6]:  # Currencies
                cell.number_format = '#,##0.00 "ج"'

    _auto_adjust_columns(ws_menu)

    # ==========================================
    # Sheet 3: 📦 المخزون والخامات (Inventory)
    # ==========================================
    ws_inv = wb.create_sheet(title="المخزون والخامات")
    inv_headers = ["كود الخامة", "اسم الخامة", "الرصيد المتاح", "وحدة القياس", "حد الإنذار الأدنى", "تكلفة الوحدة (ج)", "إجمالي القيمة التقديرية (ج)", "حالة الرصيد"]
    _setup_worksheet(ws_inv, "أرصدة خامات المخزون ومستويات إعادة الطلب", "كافيه سيزر | ceZar Coffee", inv_headers, styles)

    inv_list = db.query(InventoryItem).order_by(InventoryItem.name).all()
    for row_idx, inv in enumerate(inv_list, start=5):
        ws_inv.row_dimensions[row_idx].height = 20
        fill = styles["zebra_fill"] if row_idx % 2 == 0 else styles["white_fill"]

        stk = getattr(inv, 'current_stock', 0.0) or 0.0
        min_stk = getattr(inv, 'min_alert_stock', 0.0) or 0.0
        cost_unit = getattr(inv, 'cost_per_unit', 0.0) or 0.0
        total_val = stk * cost_unit
        status_txt = "⚠️ رصيد حرج (منخفض)" if stk <= min_stk else "✅ رصيد آمن"

        data = [
            inv.id,
            inv.name,
            stk,
            inv.unit or "وحدة",
            min_stk,
            cost_unit,
            total_val,
            status_txt
        ]

        for col_idx, val in enumerate(data, start=1):
            cell = ws_inv.cell(row=row_idx, column=col_idx, value=val)
            cell.fill = fill
            cell.border = styles["cell_border"]
            cell.font = styles["font_data"]
            cell.alignment = styles["align_center"]

            if col_idx == 2:
                cell.alignment = styles["align_right"]
                cell.font = styles["font_bold"]
            elif col_idx in [6, 7]:
                cell.number_format = '#,##0.00 "ج"'
            elif col_idx == 8 and "حرج" in status_txt:
                cell.font = Font(name="Arial", size=10, bold=True, color="DC2626")

    _auto_adjust_columns(ws_inv)

    # ==========================================
    # Sheet 4: 🧾 سجل المبيعات والطلبات (Sales & Orders)
    # ==========================================
    ws_sales = wb.create_sheet(title="سجل المبيعات")
    sales_headers = [
        "رقم الطلب", "نوع الطلب", "الترابيزة", "اسم العميل", "رقم الهاتف",
        "تفاصيل الأصناف المطلوبة", "طريقة الدفع", "الخصم (ج)", "الإجمالي المدفوع (ج)",
        "الحالة", "التاريخ والوقت"
    ]
    _setup_worksheet(ws_sales, "سجل المبيعات والطلبات الكامل", "كافيه سيزر | ceZar Coffee", sales_headers, styles)

    orders = db.query(TableOrder).filter(
        TableOrder.status != "ملغي",
        ~TableOrder.status.like("طلب حساب%"),
        TableOrder.status != "نداء ويتر",
        TableOrder.total_price > 0
    ).order_by(desc(TableOrder.id)).all()

    last_sales_row = 4
    for row_idx, o in enumerate(orders, start=5):
        last_sales_row = row_idx
        ws_sales.row_dimensions[row_idx].height = 20
        fill = styles["zebra_fill"] if row_idx % 2 == 0 else styles["white_fill"]

        c_time = (o.created_at + timedelta(hours=2)).strftime("%Y-%m-%d %I:%M %p") if o.created_at else "-"
        summary_clean = (o.items_summary or "").replace("\n", " | ")

        data = [
            o.id,
            o.order_type or "صالة",
            o.table_number if (o.table_number and o.table_number > 0) else "-",
            o.customer_name or "عميل عام",
            o.customer_phone or "-",
            summary_clean,
            o.payment_method or "كاش",
            o.discount_amount or 0.0,
            o.total_price or 0.0,
            o.status,
            c_time
        ]

        for col_idx, val in enumerate(data, start=1):
            cell = ws_sales.cell(row=row_idx, column=col_idx, value=val)
            cell.fill = fill
            cell.border = styles["cell_border"]
            cell.font = styles["font_data"]
            cell.alignment = styles["align_center"]

            if col_idx == 6:  # Items summary
                cell.alignment = styles["align_right"]
            elif col_idx in [8, 9]:
                cell.number_format = '#,##0.00 "ج"'
                if col_idx == 9:
                    cell.font = styles["font_bold"]

    # Summary row for Sales
    if len(orders) > 0:
        tot_row = last_sales_row + 1
        ws_sales.row_dimensions[tot_row].height = 24
        ws_sales.merge_cells(start_row=tot_row, start_column=1, end_row=tot_row, end_column=7)
        tot_label = ws_sales.cell(row=tot_row, column=1, value="الإجمالي الكلي للمبيعات:")
        tot_label.font = styles["font_total"]
        tot_label.alignment = styles["align_right"]
        tot_label.fill = styles["total_fill"]

        tot_val = ws_sales.cell(row=tot_row, column=9, value=f"=SUM(I5:I{last_sales_row})")
        tot_val.font = styles["font_total"]
        tot_val.fill = styles["total_fill"]
        tot_val.alignment = styles["align_center"]
        tot_val.number_format = '#,##0.00 "ج"'
        tot_val.border = styles["cell_border"]

        for col_c in range(1, len(sales_headers) + 1):
            ws_sales.cell(row=tot_row, column=col_c).fill = styles["total_fill"]
            ws_sales.cell(row=tot_row, column=col_c).border = styles["cell_border"]

    _auto_adjust_columns(ws_sales)

    # ==========================================
    # Sheet 5: 💸 المصروفات التشغيلية (Expenses)
    # ==========================================
    ws_exp = wb.create_sheet(title="المصروفات والنثريات")
    exp_headers = ["كود المصروف", "البند / البيان", "التصنيف", "المبلغ (ج)", "ملاحظات", "التاريخ والوقت"]
    _setup_worksheet(ws_exp, "سجل المصروفات التشغيلية والنثريات", "كافيه سيزر | ceZar Coffee", exp_headers, styles)

    expenses = db.query(Expense).order_by(desc(Expense.id)).all()
    last_exp_row = 4
    for row_idx, e in enumerate(expenses, start=5):
        last_exp_row = row_idx
        ws_exp.row_dimensions[row_idx].height = 20
        fill = styles["zebra_fill"] if row_idx % 2 == 0 else styles["white_fill"]

        c_time = (e.created_at + timedelta(hours=2)).strftime("%Y-%m-%d %I:%M %p") if getattr(e, "created_at", None) else "-"
        data = [
            e.id,
            e.title,
            e.category or "عام",
            e.amount or 0.0,
            e.notes or "-",
            c_time
        ]

        for col_idx, val in enumerate(data, start=1):
            cell = ws_exp.cell(row=row_idx, column=col_idx, value=val)
            cell.fill = fill
            cell.border = styles["cell_border"]
            cell.font = styles["font_data"]
            cell.alignment = styles["align_center"]

            if col_idx in [2, 5]:
                cell.alignment = styles["align_right"]
            elif col_idx == 4:
                cell.number_format = '#,##0.00 "ج"'
                cell.font = styles["font_bold"]

    # Summary row for Expenses
    if len(expenses) > 0:
        tot_row = last_exp_row + 1
        ws_exp.row_dimensions[tot_row].height = 24
        ws_exp.merge_cells(start_row=tot_row, start_column=1, end_row=tot_row, end_column=3)
        tot_lbl = ws_exp.cell(row=tot_row, column=1, value="إجمالي المصروفات والنثريات:")
        tot_lbl.font = styles["font_total"]
        tot_lbl.alignment = styles["align_right"]
        tot_lbl.fill = styles["total_fill"]

        tot_cell = ws_exp.cell(row=tot_row, column=4, value=f"=SUM(D5:D{last_exp_row})")
        tot_cell.font = styles["font_total"]
        tot_cell.fill = styles["total_fill"]
        tot_cell.alignment = styles["align_center"]
        tot_cell.number_format = '#,##0.00 "ج"'
        tot_cell.border = styles["cell_border"]

        for col_c in range(1, len(exp_headers) + 1):
            ws_exp.cell(row=tot_row, column=col_c).fill = styles["total_fill"]
            ws_exp.cell(row=tot_row, column=col_c).border = styles["cell_border"]

    _auto_adjust_columns(ws_exp)

    # ==========================================
    # Sheet 6: 👥 فريق العمل والموظفين (Staff)
    # ==========================================
    ws_staff = wb.create_sheet(title="فريق العمل")
    staff_headers = ["كود الموظف", "اسم الموظف", "الوظيفة / الدور", "الهاتف", "الراتب الأساسي (ج)", "تاريخ التعيين", "الحالة"]
    _setup_worksheet(ws_staff, "دليل الموظفين وفريق العمل ومسيرات الرواتب", "كافيه سيزر | ceZar Coffee", staff_headers, styles)

    staff_list = db.query(Employee).order_by(Employee.id).all()
    for row_idx, emp in enumerate(staff_list, start=5):
        ws_staff.row_dimensions[row_idx].height = 20
        fill = styles["zebra_fill"] if row_idx % 2 == 0 else styles["white_fill"]

        data = [
            emp.id,
            emp.name,
            emp.role,
            emp.phone or "-",
            emp.salary or 0.0,
            emp.hire_date or "-",
            emp.status
        ]

        for col_idx, val in enumerate(data, start=1):
            cell = ws_staff.cell(row=row_idx, column=col_idx, value=val)
            cell.fill = fill
            cell.border = styles["cell_border"]
            cell.font = styles["font_data"]
            cell.alignment = styles["align_center"]

            if col_idx == 2:
                cell.alignment = styles["align_right"]
                cell.font = styles["font_bold"]
            elif col_idx == 5:
                cell.number_format = '#,##0.00 "ج"'

    _auto_adjust_columns(ws_staff)

    # ==========================================
    # Sheet 7: ⏱️ سجل الورديات والشفتات (Shifts)
    # ==========================================
    ws_shifts = wb.create_sheet(title="سجل الورديات")
    shift_headers = [
        "رقم الوردية", "اسم الكاشير", "وقت الفتح", "وقت الإغلاق",
        "عهدة البداية (ج)", "مبيعات الكاش (ج)", "مبيعات الفيزا (ج)", "إجمالي المبيعات (ج)",
        "المصروفات (ج)", "الكاش الفعلي المحسوب (ج)", "الفارق (عجز/زيادة) (ج)", "الحالة"
    ]
    _setup_worksheet(ws_shifts, "أرشيف الورديات وتسويات صندوق الكاشير", "كافيه سيزر | ceZar Coffee", shift_headers, styles)

    shifts = db.query(Shift).order_by(desc(Shift.id)).all()
    for row_idx, s in enumerate(shifts, start=5):
        ws_shifts.row_dimensions[row_idx].height = 20
        fill = styles["zebra_fill"] if row_idx % 2 == 0 else styles["white_fill"]

        s_start = s.start_time.strftime("%Y-%m-%d %I:%M %p") if s.start_time else "-"
        s_end = s.end_time.strftime("%Y-%m-%d %I:%M %p") if s.end_time else "مستمرة (مفتوحة)"

        data = [
            s.id,
            s.cashier_name or "كاشير عام",
            s_start,
            s_end,
            s.starting_cash or 0.0,
            s.cash_sales or 0.0,
            s.visa_sales or 0.0,
            s.total_sales or 0.0,
            s.total_expenses or 0.0,
            s.actual_cash or 0.0,
            s.difference or 0.0,
            s.status or "مفتوحة"
        ]

        for col_idx, val in enumerate(data, start=1):
            cell = ws_shifts.cell(row=row_idx, column=col_idx, value=val)
            cell.fill = fill
            cell.border = styles["cell_border"]
            cell.font = styles["font_data"]
            cell.alignment = styles["align_center"]

            if col_idx in [5, 6, 7, 8, 9, 10, 11]:
                cell.number_format = '#,##0.00 "ج"'
                if col_idx == 8:
                    cell.font = styles["font_bold"]
                elif col_idx == 11 and (s.difference or 0.0) < 0:
                    cell.font = Font(name="Arial", size=10, bold=True, color="DC2626")

    _auto_adjust_columns(ws_shifts)

    # ==========================================
    # Sheet 8: 🤝 الموردين والشركات (Suppliers)
    # ==========================================
    ws_sup = wb.create_sheet(title="دليل الموردين")
    sup_headers = ["كود المورد", "اسم المورد", "اسم الشركة / النشاط", "رقم الهاتف", "الرصيد المالي الحالي (ج)", "ملاحظات"]
    _setup_worksheet(ws_sup, "دليل الموردين والشركات وحساباتهم المالية", "كافيه سيزر | ceZar Coffee", sup_headers, styles)

    suppliers = db.query(Supplier).order_by(Supplier.id).all()
    for row_idx, sup in enumerate(suppliers, start=5):
        ws_sup.row_dimensions[row_idx].height = 20
        fill = styles["zebra_fill"] if row_idx % 2 == 0 else styles["white_fill"]

        data = [
            sup.id,
            sup.name,
            sup.company_name or "-",
            sup.phone or "-",
            sup.current_balance or 0.0,
            sup.notes or "-"
        ]

        for col_idx, val in enumerate(data, start=1):
            cell = ws_sup.cell(row=row_idx, column=col_idx, value=val)
            cell.fill = fill
            cell.border = styles["cell_border"]
            cell.font = styles["font_data"]
            cell.alignment = styles["align_center"]

            if col_idx in [2, 3, 6]:
                cell.alignment = styles["align_right"]
            elif col_idx == 5:
                cell.number_format = '#,##0.00 "ج"'
                cell.font = styles["font_bold"]

    _auto_adjust_columns(ws_sup)

    # Save to memory buffer
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def generate_sales_excel(db, start_date=None, end_date=None) -> io.BytesIO:
    """
    Generates a dedicated Sales & Analytics Excel workbook.
    """
    if not OPENPYXL_AVAILABLE:
        raise ImportError("openpyxl is required to generate Excel files.")

    wb = Workbook()
    styles = _get_styles()

    ws = wb.active
    ws.title = "المبيعات والطلبات"
    headers = [
        "رقم الطلب", "نوع الطلب", "الترابيزة", "اسم العميل", "رقم الهاتف",
        "الأصناف والكميات", "طريقة الدفع", "الخصم (ج)", "الإجمالي المدفوع (ج)",
        "الحالة", "التاريخ والوقت"
    ]
    _setup_worksheet(ws, "تقرير سجل المبيعات والطلبات المنفذة", "كافيه سيزر | ceZar Coffee", headers, styles)

    query = db.query(TableOrder).filter(
        TableOrder.status != "ملغي",
        ~TableOrder.status.like("طلب حساب%"),
        TableOrder.status != "نداء ويتر",
        TableOrder.total_price > 0
    )

    if start_date:
        query = query.filter(TableOrder.created_at >= start_date)
    if end_date:
        query = query.filter(TableOrder.created_at <= end_date)

    orders = query.order_by(desc(TableOrder.id)).all()
    last_row = 4

    for row_idx, o in enumerate(orders, start=5):
        last_row = row_idx
        ws.row_dimensions[row_idx].height = 20
        fill = styles["zebra_fill"] if row_idx % 2 == 0 else styles["white_fill"]

        c_time = (o.created_at + timedelta(hours=2)).strftime("%Y-%m-%d %I:%M %p") if o.created_at else "-"
        summary_clean = (o.items_summary or "").replace("\n", " | ")

        data = [
            o.id,
            o.order_type or "صالة",
            o.table_number if (o.table_number and o.table_number > 0) else "-",
            o.customer_name or "عميل عام",
            o.customer_phone or "-",
            summary_clean,
            o.payment_method or "كاش",
            o.discount_amount or 0.0,
            o.total_price or 0.0,
            o.status,
            c_time
        ]

        for col_idx, val in enumerate(data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.fill = fill
            cell.border = styles["cell_border"]
            cell.font = styles["font_data"]
            cell.alignment = styles["align_center"]

            if col_idx == 6:
                cell.alignment = styles["align_right"]
            elif col_idx in [8, 9]:
                cell.number_format = '#,##0.00 "ج"'
                if col_idx == 9:
                    cell.font = styles["font_bold"]

    # Summary row
    if len(orders) > 0:
        tot_row = last_row + 1
        ws.row_dimensions[tot_row].height = 24
        ws.merge_cells(start_row=tot_row, start_column=1, end_row=tot_row, end_column=7)
        tot_label = ws.cell(row=tot_row, column=1, value="الإجمالي الكلي:")
        tot_label.font = styles["font_total"]
        tot_label.alignment = styles["align_right"]
        tot_label.fill = styles["total_fill"]

        tot_val = ws.cell(row=tot_row, column=9, value=f"=SUM(I5:I{last_row})")
        tot_val.font = styles["font_total"]
        tot_val.fill = styles["total_fill"]
        tot_val.alignment = styles["align_center"]
        tot_val.number_format = '#,##0.00 "ج"'
        tot_val.border = styles["cell_border"]

        for col_c in range(1, len(headers) + 1):
            ws.cell(row=tot_row, column=col_c).fill = styles["total_fill"]
            ws.cell(row=tot_row, column=col_c).border = styles["cell_border"]

    _auto_adjust_columns(ws)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def generate_advanced_report_excel(db, report_type="sales", start_date_str="", end_date_str="", order_type="all", payment_method="all") -> io.BytesIO:
    """
    Generates a tailored advanced report in Excel (.xlsx) format.
    Supports: 'sales', 'least_sellers', 'top_sellers', 'by_category', 'by_type'.
    """
    if not OPENPYXL_AVAILABLE:
        raise ImportError("openpyxl is required to generate Excel files.")

    wb = Workbook()
    styles = _get_styles()
    ws = wb.active
    cairo_offset = timedelta(hours=2)

    query = db.query(TableOrder).filter(
        TableOrder.status != "ملغي",
        ~TableOrder.status.like("طلب حساب%"),
        TableOrder.status != "نداء ويتر",
        TableOrder.total_price > 0
    )

    date_label_parts = []
    if start_date_str:
        try:
            dt_utc = datetime.strptime(start_date_str, "%Y-%m-%d") - cairo_offset
            query = query.filter(TableOrder.created_at >= dt_utc)
            date_label_parts.append(f"من: {start_date_str}")
        except Exception:
            pass
    if end_date_str:
        try:
            dt_utc = datetime.strptime(end_date_str + " 23:59:59", "%Y-%m-%d %H:%M:%S") - cairo_offset
            query = query.filter(TableOrder.created_at <= dt_utc)
            date_label_parts.append(f"إلى: {end_date_str}")
        except Exception:
            pass

    if order_type and order_type != "all":
        query = query.filter(TableOrder.order_type == order_type)
        date_label_parts.append(f"نوع الطلب: {order_type}")
    if payment_method and payment_method != "all":
        query = query.filter(TableOrder.payment_method.like(f"%{payment_method}%"))
        date_label_parts.append(f"طريقة الدفع: {payment_method}")

    sub_title = " | ".join(date_label_parts) if date_label_parts else "كافة الفترات والأنواع"
    orders = query.order_by(TableOrder.created_at.desc()).all()

    if report_type in ["least_sellers", "top_sellers"]:
        ws.title = "تحليل مبيعات الأصناف"
        is_least = (report_type == "least_sellers")
        sheet_title = "تقرير الأصناف الأقل مبيعاً (الراكدة)" if is_least else "تقرير الأصناف الأكثر طلباً ومبيعاً"
        headers = ["الترتيب", "اسم الصنف", "القسم / التصنيف", "سعر البيع (ج)", "إجمالي الكمية المباعة", "إجمالي الإيرادات (ج)"]
        _setup_worksheet(ws, sheet_title, sub_title, headers, styles)

        menu_items = db.query(MenuItem).all()
        menu_map = {m.name: m for m in menu_items}
        item_sales = {m.name: {"name": m.name, "category": m.category, "price": m.price, "qty": 0, "rev": 0.0} for m in menu_items}

        for o in orders:
            if o.items_summary:
                for line in o.items_summary.split("\n"):
                    if "x " in line:
                        try:
                            parts = line.split("x ", 1)
                            q = int(parts[0].strip().lstrip("- "))
                            n = parts[1].split(":")[0].split("[")[0].strip()
                            p = menu_map[n].price if n in menu_map else 0.0
                            if n not in item_sales:
                                item_sales[n] = {"name": n, "category": "أخرى", "price": p, "qty": 0, "rev": 0.0}
                            item_sales[n]["qty"] += q
                            item_sales[n]["rev"] += q * p
                        except Exception:
                            pass

        items_list = list(item_sales.values())
        if is_least:
            items_list = sorted(items_list, key=lambda x: (x["qty"], x["rev"]))
        else:
            items_list = sorted(items_list, key=lambda x: x["qty"], reverse=True)

        for idx, it in enumerate(items_list, start=5):
            ws.row_dimensions[idx].height = 20
            fill = styles["zebra_fill"] if idx % 2 == 0 else styles["white_fill"]
            data = [
                idx - 4,
                it["name"],
                it["category"] or "عام",
                it["price"] or 0.0,
                it["qty"],
                it["rev"] or 0.0
            ]
            for col_idx, val in enumerate(data, start=1):
                cell = ws.cell(row=idx, column=col_idx, value=val)
                cell.fill = fill
                cell.border = styles["cell_border"]
                cell.font = styles["font_data"]
                cell.alignment = styles["align_center"]

                if col_idx == 2:
                    cell.alignment = styles["align_right"]
                    cell.font = styles["font_bold"]
                elif col_idx in [4, 6]:
                    cell.number_format = '#,##0.00 "ج"'
                    if col_idx == 6:
                        cell.font = styles["font_bold"]

    else:
        # Default detailed sales report
        ws.title = "المبيعات المفصلة"
        headers = ["رقم الطلب", "نوع الطلب", "الترابيزة", "اسم العميل", "طريقة الدفع", "الخصم (ج)", "الإجمالي المدفوع (ج)", "الحالة", "التاريخ والوقت", "الأصناف المطلوبة"]
        _setup_worksheet(ws, "تقرير فواتير المبيعات التفصيلية", sub_title, headers, styles)

        last_row = 4
        for row_idx, o in enumerate(orders, start=5):
            last_row = row_idx
            ws.row_dimensions[row_idx].height = 20
            fill = styles["zebra_fill"] if row_idx % 2 == 0 else styles["white_fill"]

            c_time = (o.created_at + cairo_offset).strftime("%Y-%m-%d %I:%M %p") if o.created_at else "-"
            summary_clean = (o.items_summary or "").replace("\n", " | ")

            data = [
                o.id,
                o.order_type or "صالة",
                o.table_number if (o.table_number and o.table_number > 0) else "-",
                o.customer_name or "عميل عام",
                o.payment_method or "كاش",
                o.discount_amount or 0.0,
                o.total_price or 0.0,
                o.status,
                c_time,
                summary_clean
            ]

            for col_idx, val in enumerate(data, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.fill = fill
                cell.border = styles["cell_border"]
                cell.font = styles["font_data"]
                cell.alignment = styles["align_center"]

                if col_idx in [4, 10]:
                    cell.alignment = styles["align_right"]
                elif col_idx in [6, 7]:
                    cell.number_format = '#,##0.00 "ج"'
                    if col_idx == 7:
                        cell.font = styles["font_bold"]

        # Summary total row
        if len(orders) > 0:
            tot_row = last_row + 1
            ws.row_dimensions[tot_row].height = 24
            ws.merge_cells(start_row=tot_row, start_column=1, end_row=tot_row, end_column=6)
            lbl = ws.cell(row=tot_row, column=1, value="الإجمالي الكلي للفواتير المفلترة:")
            lbl.font = styles["font_total"]
            lbl.alignment = styles["align_right"]
            lbl.fill = styles["total_fill"]

            tot_val = ws.cell(row=tot_row, column=7, value=f"=SUM(G5:G{last_row})")
            tot_val.font = styles["font_total"]
            tot_val.fill = styles["total_fill"]
            tot_val.alignment = styles["align_center"]
            tot_val.number_format = '#,##0.00 "ج"'
            tot_val.border = styles["cell_border"]

            for col_c in range(1, len(headers) + 1):
                ws.cell(row=tot_row, column=col_c).fill = styles["total_fill"]
                ws.cell(row=tot_row, column=col_c).border = styles["cell_border"]

    _auto_adjust_columns(ws)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output

