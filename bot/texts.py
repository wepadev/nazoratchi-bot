"""Botdagi asosiy matnlar va tugma yozuvlari (o'zbek tilida, lotin yozuvi)."""

# ---- Asosiy menyu tugmalari ----
BTN_SHARE_PHONE = "📱 Telefon raqamni yuborish"
BTN_TESTS = "📝 Testlar"
BTN_RATING = "🏆 Reyting"
BTN_JOIN = "➕ Guruhga qo'shilish"
BTN_MY_GROUPS = "📚 Guruhlarim"
BTN_PROFILE = "👤 Profil"
BTN_GROUPS = "🗂 Guruhlar"
BTN_CREATE_GROUP = "🆕 Guruh yaratish"
BTN_ADMINS = "👮 Nazoratchilar"
BTN_ACTIVITY = "📈 Faoliyat"
BTN_APPEALS = "📨 E'tirozlar"
BTN_CANCEL = "✖️ Bekor qilish"
BTN_SKIP = "⏭ O'tkazib yuborish"

# ---- Ro'yxatdan o'tish ----
WELCOME = (
    "Assalomu alaykum! 👋\n\n"
    "Botdan foydalanish uchun qisqa ro'yxatdan o'ting.\n"
    "Pastdagi <b>«{btn}»</b> tugmasini bosing."
).format(btn=BTN_SHARE_PHONE)
SHARE_OWN_CONTACT = "Iltimos, aynan <b>o'zingizning</b> raqamingizni pastdagi tugma orqali yuboring."
PHONE_TAKEN = "Bu telefon raqam boshqa hisobga biriktirilgan. Muammo bo'lsa, adminga murojaat qiling."
ASK_FULL_NAME = "Rahmat! Endi <b>ism va familiyangizni</b> yozing.\n\nMasalan: <i>Aliyev Valijon</i>"
BAD_FULL_NAME = "Ism-familiya 3–64 belgi oralig'ida bo'lishi kerak. Qaytadan yozing."
REGISTERED = "✅ Ro'yxatdan o'tdingiz, <b>{name}</b>!"
REGISTERED_USER_HINT = "\n\nGuruhga qo'shilish uchun nazoratchi bergan kodni «{btn}» orqali kiriting.".format(
    btn=BTN_JOIN)
MAIN_MENU = "Asosiy menyu 👇"
CANCELLED = "Bekor qilindi."

# ---- Ustoz ----
ASK_CODE = "Nazoratchi bergan <b>guruh kodini</b> yuboring.\n\nMasalan: <code>K7M2QX</code>"
CODE_NOT_FOUND = "❌ Bunday kod topilmadi. Kodni tekshirib, qaytadan yuboring."
JOINED = "🎉 Siz <b>{name}</b> guruhiga qo'shildingiz!"
ALREADY_MEMBER = "Siz allaqachon <b>{name}</b> guruhi a'zosisiz."
NO_GROUPS_USER = "Siz hali hech qaysi guruhga qo'shilmagansiz.\n«{btn}» tugmasini bosing.".format(btn=BTN_JOIN)
LEFT_GROUP = "Siz <b>{name}</b> guruhidan chiqdingiz."
CONFIRM_LEAVE = ("⚠️ <b>{name}</b> guruhidan chiqasizmi?\n"
                 "Bu guruhdagi tangalaringiz reytingda ko'rinmay qoladi.")
NO_ACTIVE_TESTS = "Hozir faol test yo'q. Yangi test nashr qilinganda bot o'zi xabar beradi. 🔔"
ASK_ANSWERS = (
    "✍️ <b>{title}</b> — {n} ta savol\n\n"
    "Javoblaringizni bitta xabarda yuboring:\n"
    "• ketma-ket: <code>abcdabcd...</code>\n"
    "• yoki raqam bilan: <code>1a 2b 3c ...</code>\n\n"
    "Javob bermagan savolga <code>x</code> yozing (raqamli formatda shunchaki tashlab keting).\n"
    "Keyingi safar tugmasiz ham bo'ladi: <code>{code}*abcd...</code>\n"
    "Muddat: {deadline} ({left} qoldi)"
)
CONFIRM_ANSWERS = ("Javoblaringizni tekshiring:\n{preview}\n"
                   "{blank}⚠️ Tasdiqlagandan keyin o'zgartirib bo'lmaydi.")
SUBMITTED = ("✅ Javoblaringiz qabul qilindi!\n\n"
             "Natija: <b>{correct}/{n}</b> (+{coins} 🪙)\n\n"
             "Qaysi savollarda xato qilganingiz va to'g'ri javoblar muddat tugagach yuboriladi.")
ALREADY_SUBMITTED = "Siz bu testni allaqachon topshirgansiz: {correct}/{n}."
TEST_NOT_ACTIVE = "Bu test faol emas yoki muddati tugagan."
ASK_APPEAL = ("⚖️ <b>E'tiroz</b>\n\nQaysi savol bo'yicha va nima uchun? Bitta xabarda yozing.\n"
              "Masalan: <i>14 — to'g'ri javob B bo'lishi kerak, chunki ...</i>")
APPEAL_SENT = "✅ E'tirozingiz nazoratchiga yuborildi. Javobini bot orqali olasiz."

# ---- Admin / nazoratchi ----
ASK_GROUP_NAME = "Yangi guruh <b>nomini</b> yozing:"
BAD_NAME = "Nom 2–64 belgi oralig'ida bo'lishi kerak."
NO_GROUPS_ADMIN = "Sizga hali guruh tayinlanmagan. Bosh admin tayinlashini kuting."
NO_GROUPS_SUPER = "Hali guruh yo'q. «{btn}» tugmasini bosing.".format(btn=BTN_CREATE_GROUP)
GROUPS_TITLE = "🗂 <b>Guruhlar</b> — tanlang:"
NOT_FOUND = "Topilmadi yoki sizga ruxsat yo'q."
NEW_MEMBER_NOTIFY = "🔔 <b>{group}</b> guruhiga yangi ustoz qo'shildi: {name} ({phone})"
ASK_TEST_TITLE = "Yangi test <b>nomini</b> yozing.\n\nMasalan: <i>1-hafta: Logarifmlar</i>"
ASK_TEST_FILE = ("Test <b>faylini</b> yuboring (PDF yoki rasm).\n"
                 "Fayl bo'lmasa — «{btn}» ni bosing.").format(btn=BTN_SKIP)
ASK_TEST_KEY = ("Endi <b>javoblar kalitini</b> yuboring:\n"
                "• ketma-ket: <code>abcdabcd...</code>\n"
                "• yoki: <code>1a 2b 3c ...</code>\n\n"
                "Savollar soni kalitdan avtomatik aniqlanadi.")
ASK_DEADLINE_DATE = ("Muddatni yozing (Toshkent vaqti):\n"
                     "<code>25.11.2026 18:00</code> yoki <code>25.11 18:00</code>")
BAD_DEADLINE = "Sana noto'g'ri yoki o'tib ketgan. Masalan: <code>25.11 18:00</code>"
ASK_FIX_KEY = ("🔑 Qaysi savollarning javobini o'zgartirasiz?\n"
               "Masalan: <code>14c</code> yoki <code>14c 20a</code>\n\n"
               "Hamma natijalar qayta hisoblanadi va tangalar avtomatik to'g'rilanadi.")
ASK_COINS = ("🪙 <b>{name}</b> uchun tanga miqdori va sababini yozing:\n"
             "<code>+3 Darsda faol qatnashgani uchun</code>\n"
             "<code>-2 Qoidabuzarlik</code>")
BAD_COINS = "Format: <code>+3 sabab</code> yoki <code>-2 sabab</code>. Sabab majburiy."

# ---- Bosh admin ----
ASK_ADMIN_PHONE = (
    "Nazoratchi qilmoqchi bo'lgan foydalanuvchining <b>telefon raqamini</b> yoki "
    "<b>Telegram ID</b>sini yuboring.\n\nU avval botda ro'yxatdan o'tgan bo'lishi kerak."
)
ADMIN_USER_NOT_FOUND = "Bunday foydalanuvchi topilmadi. U avval botda ro'yxatdan o'tishi kerak."
YOU_ARE_ADMIN_NOW = "🎉 Sizga nazoratchi huquqi berildi! Menyu yangilandi."
YOU_ARE_NOT_ADMIN = "Sizning nazoratchi huquqingiz olib tashlandi."
YOU_ASSIGNED = "📌 Siz <b>{name}</b> guruhiga nazoratchi etib tayinlandingiz."
