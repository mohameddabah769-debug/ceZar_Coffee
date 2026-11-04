import sys

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from sqlalchemy.orm import Session
from .models import MenuItem, InventoryItem, PromoCode

CEZAR_MENU_DATA = [
    # 0. الكوفى (Hot Coffee)
    {"category": "الكوفى", "name": "اسبريسو سنجل", "price": 35, "description": "شوت إسبريسو نقي ومركز"},
    {"category": "الكوفى", "name": "اسبريسو دبل", "price": 55, "description": "دبل شوت إسبريسو لتركيز وطاقة أعلى"},
    {"category": "الكوفى", "name": "اسبريسو ميكاتو", "price": 60, "description": "إسبريسو مع لمسة رغوة حليب ناعمة"},
    {"category": "الكوفى", "name": "اسبريسو فلات وايت", "price": 60, "description": "إسبريسو دبل مع حليب مبخر كريمي"},
    {"category": "الكوفى", "name": "اسبريسو كراميل ميكاتو", "price": 60, "description": "إسبريسو مع حليب وصوص كراميل ذهبي"},
    {"category": "الكوفى", "name": "اسبريسو كورتادو", "price": 60, "description": "إسبريسو مع حليب مبخر بنسب متساوية"},
    {"category": "الكوفى", "name": "قهوة تركى سنجل", "price": 35, "description": "قهوة تركي ببن سيزر الفاخر والمحبب"},
    {"category": "الكوفى", "name": "قهوة تركى دبل", "price": 50, "description": "فنجان قهوة تركي دبل لمزاج عالي"},
    {"category": "الكوفى", "name": "قهوة فرنساوى", "price": 50, "description": "قهوة باللبن المبخر الناعم"},
    {"category": "الكوفى", "name": "قهوة فليفر", "price": 55, "description": "قهوة تركي بنكهات (بندق / فانيليا / كراميل)"},
    {"category": "الكوفى", "name": "نسكافية بلاك", "price": 40, "description": "نسكافيه كلاسيك ساخن وسادة"},
    {"category": "الكوفى", "name": "نسكافية حليب", "price": 55, "description": "نسكافيه ممزوج بالحليب الساخن"},
    {"category": "الكوفى", "name": "نسكافية فليفر", "price": 60, "description": "نسكافيه بحليب ونكهة (فانيليا / كراميل / بندق)"},
    {"category": "الكوفى", "name": "لاتيه كلاسيك", "price": 65, "description": "قهوة بالحليب ورغوة ناعمة"},
    {"category": "الكوفى", "name": "لاتيه فليفر", "price": 70, "description": "لاتيه ساخن بنكهتك المفضلة"},
    {"category": "الكوفى", "name": "كابتشينو كلاسيك", "price": 60, "description": "كابتشينو إيطالي غني بالرغوة ورشة كاكاو"},
    {"category": "الكوفى", "name": "كابتشينو فليفر", "price": 65, "description": "كابتشينو بنكهة كراميل أو فانيليا أو بندق"},
    {"category": "الكوفى", "name": "موكا", "price": 65, "description": "مزيج الإسبريسو مع الشوكولاتة والحليب الساخن"},
    {"category": "الكوفى", "name": "امريكان كوفى", "price": 60, "description": "قهوة أمريكان ساخنة ومفلترة على أصولها"},

    # 00. مشروبات ساخنة
    {"category": "مشروبات ساخنة", "name": "شاى", "price": 20, "description": "شاي مصري بالنعناع أو سادة"},
    {"category": "مشروبات ساخنة", "name": "شاى كرك", "price": 30, "description": "شاي هندي مبهر بالحليب والهيل والزعفران"},
    {"category": "مشروبات ساخنة", "name": "شاى حليب", "price": 40, "description": "شاي بحليب ساخن كامل الدسم"},
    {"category": "مشروبات ساخنة", "name": "شاى نكهات", "price": 25, "description": "شاي بنكهات خوخ / توت / ليمون"},
    {"category": "مشروبات ساخنة", "name": "أعشاب", "price": 25, "description": "يانسون / كركديه / نعناع / تليو / بابونج"},
    {"category": "مشروبات ساخنة", "name": "ميكس اعشاب", "price": 40, "description": "توليفة أعشاب مهدئة ومريحة"},
    {"category": "مشروبات ساخنة", "name": "ليمون عسل", "price": 30, "description": "ليمون دافئ محلى بعسل النحل الطبيعي"},
    {"category": "مشروبات ساخنة", "name": "سحلب مكسرات", "price": 55, "description": "سحلب بلبن وقشطة ومكسرات محمصة وقرفة"},
    {"category": "مشروبات ساخنة", "name": "سحلب فواكه", "price": 65, "description": "سحلب ساخن غني بقطع الفواكه الطازجة"},
    {"category": "مشروبات ساخنة", "name": "سحلب شوكليت", "price": 55, "description": "سحلب ساخن مع صوص شوكولاتة فاخر"},
    {"category": "مشروبات ساخنة", "name": "هوت شوكليت", "price": 60, "description": "شوكولاتة ساخنة غنية وكريمية"},
    {"category": "مشروبات ساخنة", "name": "هوت اوريو", "price": 70, "description": "مشروب الأوريو الساخن بالشوكولاتة والكريمة"},
    {"category": "مشروبات ساخنة", "name": "هوت بوريو", "price": 65, "description": "بوريو ساخن مع الحليب والشوكولاتة الذائبة"},
    {"category": "مشروبات ساخنة", "name": "هوت كيت كات", "price": 75, "description": "شوكولاتة كيت كات المذابة مع الحليب الدافئ"},
    {"category": "مشروبات ساخنة", "name": "هوت هوهوز", "price": 60, "description": "هوهوز ساخن غرقان في الحليب والشوكولاتة"},
    {"category": "مشروبات ساخنة", "name": "ابل سيدر", "price": 50, "description": "عصير تفاح ساخن مع أعواد القرفة والقرنفل"},

    # 1. أيس كوفي
    {"category": "أيس كوفي", "name": "أيس لاتيه كلاسيك", "price": 65, "description": "إسبريسو مع حليب بارد وثلج"},
    {"category": "أيس كوفي", "name": "أيس لاتيه فليفر", "price": 70, "description": "أيس لاتيه بنكهة فانيليا أو كراميل أو بندق"},
    {"category": "أيس كوفي", "name": "سبانش لاتيه بارد", "price": 75, "description": "إسبريسو مع حليب مكثف محلى وحليب بارد"},
    {"category": "أيس كوفي", "name": "أيس موكا شوكليت", "price": 70, "description": "إسبريسو مع صوص شوكولاتة وحليب وثلج"},
    {"category": "أيس كوفي", "name": "أيس وايت موكا", "price": 75, "description": "إسبريسو مع صوص شوكولاتة بيضاء وحليب بارد"},
    {"category": "أيس كوفي", "name": "أيس امريكانو", "price": 50, "description": "شوت إسبريسو مزدوج مع ماء مثلج ومنعش"},

    # 2. ميلك شيك
    {"category": "ميلك شيك", "name": "ميلك شيك فانيليا", "price": 65, "description": "أيس كريم فانيليا مع حليب وكريمة مخفوقة"},
    {"category": "ميلك شيك", "name": "ميلك شيك شوكولاتة", "price": 65, "description": "أيس كريم شوكولاتة مع صوص فادج غني"},
    {"category": "ميلك شيك", "name": "ميلك شيك فراولة", "price": 65, "description": "أيس كريم فراولة طبيعية مع صوص فراولة"},
    {"category": "ميلك شيك", "name": "ميلك شيك أوريو", "price": 75, "description": "بسكويت أوريو مطحون مع أيس كريم وشوكولاتة"},
    {"category": "ميلك شيك", "name": "ميلك شيك لوتس", "price": 80, "description": "بسكويت لوتس وزبدة لوتس أصلية مع الكريمة"},
    {"category": "ميلك شيك", "name": "ميلك شيك كيت كات", "price": 80, "description": "أصابع كيت كات مع أيس كريم وكريمة"},

    # 3. ميكسات فريش وموهيتو
    {"category": "ميكسات فريش", "name": "موهيتو كلاسيك نعناع", "price": 55, "description": "سفن أب مع ليمون ونعناع فريش وثلج مجروش"},
    {"category": "ميكسات فريش", "name": "موهيتو بلوبيري (توت أزرق)", "price": 60, "description": "موهيتو منعش مع سيرب توت أزرق"},
    {"category": "ميكسات فريش", "name": "موهيتو فراولة", "price": 60, "description": "موهيتو مع قطع فراولة وسيرب فراولة مركز"},
    {"category": "ميكسات فريش", "name": "موهيتو بطيخ", "price": 60, "description": "موهيتو بنكهة البطيخ المنعشة للصيف"},
    {"category": "ميكسات فريش", "name": "ريد بول بطيخ / توت", "price": 75, "description": "مشروب الطاقة ريد بول مع نكهتك المفضلة وثلج"},
    {"category": "ميكسات فريش", "name": "سموذي مانجو فريش", "price": 60, "description": "مانجو طبيعية مثلجة وسميكة"},
    {"category": "ميكسات فريش", "name": "سموذي فراولة فريش", "price": 60, "description": "فراولة بيوريه مثلجة ومنعشة"},
    {"category": "ميكسات فريش", "name": "عصير برتقال فريش", "price": 45, "description": "برتقال طبيعي 100% معصور فريش"},
    {"category": "ميكسات فريش", "name": "ليمون نعناع فريش", "price": 40, "description": "عصير ليمون ونعناع مثلج ومنعش"},

    # 4. الحلويات والوافلز
    {"category": "وافلز", "name": "وافل نوتيلا كلاسيك", "price": 75, "description": "وافل بلجيكي مقرمش غرقان نوتيلا أصلية"},
    {"category": "وافلز", "name": "وافل لوتس بلجيكي", "price": 85, "description": "وافل بزبدة وبسكويت لوتس مقرمش"},
    {"category": "وافلز", "name": "وافل ميكس شوكليت (أبيض وبني)", "price": 85, "description": "وافل بنوتيلا وشوكولاتة بلجيكية بيضاء"},
    {"category": "وافلز", "name": "وافل فواكه نوتيلا", "price": 95, "description": "وافل نوتيلا مع قطع موز وفراولة طازجة"},
    {"category": "وافلز", "name": "كريب نوتيلا بالموز", "price": 80, "description": "كريب فرنسي طري محشو نوتيلا وموز ومكسرات"},
    {"category": "وافلز", "name": "بان كيك ميني شوكولاتة", "price": 70, "description": "قطع ميني بان كيك هشة مع صوص شوكولاتة"},
    {"category": "وافلز", "name": "أم علي بالمكسرات والقشطة", "price": 65, "description": "أم علي ساخنة باللبن والقشطة الفلاحي والمكسرات"},
    {"category": "وافلز", "name": "مولتن كيك فادج", "price": 85, "description": "كيك شوكولاتة ساخن محشو لافا ذائبة مع بولة أيس كريم"},
    {"category": "وافلز", "name": "تشيز كيك بلوبيري", "price": 75, "description": "تشيز كيك كريمي مع صوص التوت الأزرق الفاخر"},

    # 5. شيشة
    {"category": "شيشة", "name": "شيشة سلوم", "price": 40, "description": "شيشة سلوم مصرية على أصولها"},
    {"category": "شيشة", "name": "شيشة قص", "price": 45, "description": "معسل قص أصلي ومظبوط"},
    {"category": "شيشة", "name": "شيشة فاخر", "price": 70, "description": "معسل فاخر بنكهات التفاحتين، عنب، خوخ، بطيخ"},
    {"category": "شيشة", "name": "شيشة فاخر ميكس", "price": 85, "description": "ميكس نكهات فاخرة حسب اختيارك"}
]

DEFAULT_INVENTORY = [
    {"name": "بن إسبريسو كولومبي فاخر", "unit": "كجم", "current_stock": 18.5, "min_alert_stock": 5.0, "cost_per_unit": 450.0},
    {"name": "بن تركي سيزر خصوصي", "unit": "كجم", "current_stock": 12.0, "min_alert_stock": 4.0, "cost_per_unit": 380.0},
    {"name": "حليب كامل الدسم مبخر", "unit": "لتر", "current_stock": 42.0, "min_alert_stock": 10.0, "cost_per_unit": 38.0},
    {"name": "سكر أبيض ناعم", "unit": "كجم", "current_stock": 25.0, "min_alert_stock": 8.0, "cost_per_unit": 35.0},
    {"name": "شوكولاتة نوتيلا أصلية", "unit": "علبة", "current_stock": 6.0, "min_alert_stock": 2.0, "cost_per_unit": 280.0},
    {"name": "زبدة وبسكويت لوتس", "unit": "علبة", "current_stock": 4.0, "min_alert_stock": 2.0, "cost_per_unit": 220.0},
    {"name": "سيرب فانيليا وبندق وكراميل", "unit": "زجاجة", "current_stock": 8.0, "min_alert_stock": 3.0, "cost_per_unit": 180.0},
    {"name": "أكواب تيك أواي 12oz بغطاء", "unit": "كرتونة", "current_stock": 5.0, "min_alert_stock": 2.0, "cost_per_unit": 350.0},
    {"name": "مناديل وشاليموه كافيه", "unit": "باكت", "current_stock": 15.0, "min_alert_stock": 4.0, "cost_per_unit": 90.0},
    {"name": "علب مشروب الطاقة ريد بول", "unit": "علبة", "current_stock": 24.0, "min_alert_stock": 6.0, "cost_per_unit": 45.0},
]

DEFAULT_PROMO_CODES = [
    {"code": "CEZAR10", "discount_type": "percentage", "discount_value": 10.0, "min_order_value": 50.0},
    {"code": "WELCOME", "discount_type": "percentage", "discount_value": 15.0, "min_order_value": 70.0},
    {"code": "VIP", "discount_type": "percentage", "discount_value": 20.0, "min_order_value": 100.0},
    {"code": "COFFEE20", "discount_type": "fixed", "discount_value": 20.0, "min_order_value": 80.0},
]


def seed_menu(db: Session):
    count = db.query(MenuItem).count()
    if count == 0:
        for item in CEZAR_MENU_DATA:
            db_item = MenuItem(
                category=item["category"],
                name=item["name"],
                price=float(item["price"]),
                description=item.get("description"),
                is_available=True
            )
            db.add(db_item)
        db.commit()

    # Seed Inventory
    if db.query(InventoryItem).count() == 0:
        for inv in DEFAULT_INVENTORY:
            db.add(InventoryItem(
                name=inv["name"],
                unit=inv["unit"],
                current_stock=inv["current_stock"],
                min_alert_stock=inv["min_alert_stock"],
                cost_per_unit=inv["cost_per_unit"]
            ))
        db.commit()

    # Seed Promo Codes
    if db.query(PromoCode).count() == 0:
        for p in DEFAULT_PROMO_CODES:
            db.add(PromoCode(
                code=p["code"],
                discount_type=p["discount_type"],
                discount_value=p["discount_value"],
                min_order_value=p["min_order_value"],
                is_active=True
            ))
        db.commit()
