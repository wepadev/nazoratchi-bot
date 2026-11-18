# Botni internetga joylash (Railway)

Bot 24/7 ishlashi uchun Railway hostingidan foydalanamiz. Kod tayyor (Dockerfile, railway.json) —
faqat quyidagi tugmalarni bosish kerak. Narxi: oyiga taxminan $5 (Hobby tarif).

## 1. Ro'yxatdan o'tish
1. railway.com saytiga kiring → **Login** → **GitHub** orqali kiring.
2. GitHub so'raganda Railway'ga `nazoratchi-bot` repozitoriyasiga ruxsat bering.

## 2. Loyiha yaratish
1. **New Project** → **Deploy from GitHub repo** → `nazoratchi-bot` ni tanlang.
2. Xizmat (service) ochilgach: **Settings** → **Source** → **Branch** — `claude/blissful-planck-ty0f5n`
   (yoki kod `main` ga birlashtirilgan bo'lsa — `main`).

## 3. Sozlamalar (Variables)
Xizmatning **Variables** bo'limida **New Variable** orqali ikkitasini qo'shing:

| Nomi | Qiymati |
|---|---|
| `BOT_TOKEN` | BotFather bergan token |
| `SUPER_ADMIN_IDS` | @userinfobot bergan ID raqamingiz |

Token faqat shu yerga yoziladi — hech kimga yubormang.

## 4. Doimiy disk (ma'lumotlar o'chib ketmasligi uchun)
Xizmat ustida o'ng tugma (yoki **Ctrl/Cmd + K**) → **Volume** / **Attach Volume** →
**Mount path**: `/app/data`

Bu bo'lmasa, har yangilanishda ro'yxatdan o'tganlar va natijalar o'chib ketadi.

## 5. Ishga tushirish
**Deploy** tugmasini bosing. 1–3 daqiqadan keyin **Deployments → View Logs** da
`Start polling` yozuvi chiqsa — bot ishlayapti. Telegram'da botga `/start` yozing.

## Muhim
- Bot bir vaqtda faqat **bitta joyda** ishlashi kerak. Kompyuterda ham ishga tushirsangiz,
  Telegram xato beradi (`Conflict`). Kompyuterdagisini to'xtating.
- Kodni yangilasak, Railway o'zi qayta o'rnatadi — sizdan hech narsa talab qilinmaydi.

---

# Mini App'ni yoqish (Northflank)

1. Xizmat → **Networking** → **Add port**: port `8080`, protocol **HTTP**, **Publicly expose** yoqilgan → saqlang.
2. Northflank ochiq manzil beradi (masalan `https://p01--nazoratchi-bot--xxxx.code.run`). Uni nusxalang.
3. **Environment** → `WEBAPP_URL` = shu manzil (oxirida `/` siz) → **Update & restart**.
4. Telegram'da botni qayta oching: pastki chap burchakda **Ilova** tugmasi chiqadi.
