# Nazoratchi bot

Telegram bot: foydalanuvchilar ro'yxatdan o'tadi, adminlar guruh yaratadi,
foydalanuvchilar admin bergan **kod** orqali guruhga qo'shiladi.

## Imkoniyatlar

**Foydalanuvchi**
- Ro'yxatdan o'tish: telefon raqam (faqat o'zining, Telegram tugmasi orqali) + ism-familiya
- ➕ Guruhga qo'shilish — 6 belgili kod orqali (katta-kichik harf farqi yo'q)
- 📚 Mening guruhlarim — ro'yxat va guruhdan chiqish
- 👤 Profil

**Admin**
- 🆕 Guruh yaratish — avtomatik noyob kod beriladi
- 🗂 Guruhlarni boshqarish — a'zolar ro'yxati (ism, telefon), a'zoni chiqarish,
  yangi kod (eskisi bekor bo'ladi), nomini o'zgartirish, o'chirish
- Guruhga yangi a'zo qo'shilganda bildirishnoma

**Bosh admin** (`.env` dagi `SUPER_ADMIN_IDS`)
- Admin huquqlari + barcha guruhlarni ko'radi
- 👮 Adminlar — telefon raqam yoki Telegram ID orqali admin qo'shish / olib tashlash

## Ishga tushirish

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # BOT_TOKEN va SUPER_ADMIN_IDS ni to'ldiring
python -m bot
```

Testlar: `pip install pytest && python -m pytest -q`

## Tuzilma

```
bot/
  __main__.py        ishga tushirish
  config.py          .env sozlamalari
  db.py              SQLite (users, groups, group_members)
  texts.py           barcha matnlar (o'zbekcha)
  keyboards.py       tugmalar
  theme.py           brend ranglari va shriftlari (Mini App uchun)
  middlewares.py     har bir so'rovga db / foydalanuvchi / huquqlar
  handlers/          common (start, ro'yxat), user, admin, superadmin
```
