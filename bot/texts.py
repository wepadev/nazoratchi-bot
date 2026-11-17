"""Botdagi barcha matnlar (o'zbek tilida, lotin yozuvi)."""

# ---- Tugmalar ----
BTN_SHARE_PHONE = "📱 Telefon raqamni yuborish"
BTN_JOIN = "➕ Guruhga qo'shilish"
BTN_MY_GROUPS = "📚 Mening guruhlarim"
BTN_PROFILE = "👤 Profil"
BTN_CREATE_GROUP = "🆕 Guruh yaratish"
BTN_MANAGE_GROUPS = "🗂 Guruhlarni boshqarish"
BTN_ADMINS = "👮 Adminlar"
BTN_CANCEL = "✖️ Bekor qilish"

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
REGISTERED = "✅ Ro'yxatdan o'tdingiz, <b>{name}</b>!\n\nGuruhga qo'shilish uchun admin bergan kodni kiriting."
MAIN_MENU = "Asosiy menyu 👇"
CANCELLED = "Bekor qilindi."
NEED_REGISTER = "Avval ro'yxatdan o'ting: /start"

# ---- Foydalanuvchi ----
ASK_CODE = "Admin bergan <b>guruh kodini</b> yuboring.\n\nMasalan: <code>K7M2QX</code>"
CODE_NOT_FOUND = "❌ Bunday kod topilmadi. Kodni tekshirib, qaytadan yuboring."
JOINED = "🎉 Siz <b>{name}</b> guruhiga qo'shildingiz!"
ALREADY_MEMBER = "Siz allaqachon <b>{name}</b> guruhi a'zosisiz."
NO_GROUPS_USER = "Siz hali hech qaysi guruhga qo'shilmagansiz.\n«{btn}» tugmasini bosing.".format(btn=BTN_JOIN)
MY_GROUPS_TITLE = "📚 <b>Mening guruhlarim</b>"
LEFT_GROUP = "Siz <b>{name}</b> guruhidan chiqdingiz."
PROFILE = (
    "👤 <b>Profil</b>\n\n"
    "Ism: <b>{name}</b>\n"
    "Telefon: <code>{phone}</code>\n"
    "Holat: {role}\n"
    "Guruhlar soni: {groups}"
)
ROLE_USER = "foydalanuvchi"
ROLE_ADMIN = "admin"
ROLE_SUPER = "bosh admin"

# ---- Admin: guruhlar ----
ASK_GROUP_NAME = "Yangi guruh <b>nomini</b> yozing:"
BAD_GROUP_NAME = "Guruh nomi 2–64 belgi oralig'ida bo'lishi kerak."
GROUP_CREATED = (
    "✅ Guruh yaratildi!\n\n"
    "Nomi: <b>{name}</b>\n"
    "Qo'shilish kodi: <code>{code}</code>\n\n"
    "Shu kodni foydalanuvchilarga bering — ular botda «{btn}» orqali kiritadi."
)
NO_GROUPS_ADMIN = "Sizda hali guruh yo'q. «{btn}» tugmasini bosing.".format(btn=BTN_CREATE_GROUP)
GROUPS_TITLE = "🗂 <b>Guruhlar</b> — boshqarish uchun tanlang:"
GROUP_CARD = (
    "📁 <b>{name}</b>\n\n"
    "Kod: <code>{code}</code>\n"
    "A'zolar: {count} ta"
)
MEMBERS_TITLE = "👥 <b>{name}</b> — a'zolar ({count}):"
NO_MEMBERS = "Bu guruhda hali a'zo yo'q."
CODE_REGENERATED = "🔄 Yangi kod: <code>{code}</code>\nEski kod endi ishlamaydi."
CONFIRM_DELETE = "⚠️ <b>{name}</b> guruhini o'chirasizmi? A'zolar ro'yxati ham o'chadi."
GROUP_DELETED = "🗑 Guruh o'chirildi."
ASK_RENAME = "Guruhning yangi nomini yozing:"
RENAMED = "✏️ Guruh nomi o'zgartirildi: <b>{name}</b>"
MEMBER_REMOVED = "A'zo guruhdan chiqarildi."
NOT_FOUND = "Topilmadi yoki sizga ruxsat yo'q."
NEW_MEMBER_NOTIFY = "🔔 <b>{group}</b> guruhiga yangi a'zo qo'shildi: {name} ({phone})"

# ---- Bosh admin: adminlar ----
ADMINS_TITLE = "👮 <b>Adminlar</b>"
NO_ADMINS = "Hozircha qo'shimcha admin yo'q."
ASK_ADMIN_PHONE = (
    "Admin qilmoqchi bo'lgan foydalanuvchining <b>telefon raqamini</b> yoki "
    "<b>Telegram ID</b>sini yuboring.\n\nU avval botda ro'yxatdan o'tgan bo'lishi kerak."
)
ADMIN_USER_NOT_FOUND = "Bunday foydalanuvchi topilmadi. U avval botda ro'yxatdan o'tishi kerak."
ADMIN_ADDED = "✅ <b>{name}</b> admin qilindi."
ADMIN_ALREADY = "<b>{name}</b> allaqachon admin."
ADMIN_REMOVED = "<b>{name}</b> adminlikdan olindi."
YOU_ARE_ADMIN_NOW = "🎉 Sizga admin huquqi berildi! Menyu yangilandi."
YOU_ARE_NOT_ADMIN = "Sizning admin huquqingiz olib tashlandi."
CANT_REMOVE_SUPER = "Bosh adminni bot orqali olib bo'lmaydi (u sozlamalarda belgilangan)."

# ---- Inline tugmalar ----
IB_MEMBERS = "👥 A'zolar"
IB_NEW_CODE = "🔄 Yangi kod"
IB_RENAME = "✏️ Nomini o'zgartirish"
IB_DELETE = "🗑 O'chirish"
IB_BACK = "⬅️ Orqaga"
IB_YES_DELETE = "Ha, o'chirish"
IB_NO = "Yo'q"
IB_LEAVE = "🚪 Guruhdan chiqish"
IB_ADD_ADMIN = "➕ Admin qo'shish"
IB_REMOVE = "❌"
