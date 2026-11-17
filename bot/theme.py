"""Brend uslubi (ranglar, shriftlar, burchak radiuslari) — bitta joyda.

Telegram chatining o'zida rang va shriftni o'zgartirib bo'lmaydi. Bu qiymatlar
Mini App (Web App) sahifalari va bot yaratadigan rasmlar (masalan, guruh kodi
kartochkasi) uchun ishlatiladi.
"""

LIGHT = {
    "brand": "#285EE7",          # asosiy ko'k: tugmalar, havolalar
    "brand_strong": "#1948C2",   # hover / bosilgan holat
    "brand_edge": "#10369D",
    "tint": "#E9F0FF",           # och ko'k fon (belgilangan elementlar)
    "accent": "#FABD54",         # sariq urg'u
    "accent_strong": "#986900",
    "accent_soft": "#FFF8EF",
    "marker": "#FFE27A",
    "page": "#F6F8FB",           # sahifa foni
    "surface": "#FFFFFF",        # kartochkalar
    "surface_soft": "#F4F8FE",
    "raised": "#EDF0F6",
    "ink": "#1A2438",            # asosiy matn
    "muted": "#5B6374",          # ikkinchi darajali matn
    "line": "#DFE3EA",           # chegaralar
    "line_strong": "#A4ABB9",
    "success": "#01683F",
    "success_soft": "#F1FBF4",
    "danger": "#A5001C",
    "danger_soft": "#FFF5F4",
    "hero": "#285EE7",
}

DARK = {
    "brand": "#76A2FE",
    "brand_strong": "#A7C4FE",
    "brand_edge": "#285EE7",
    "tint": "#172B58",
    "accent": "#FABD54",
    "accent_strong": "#FBD08E",
    "accent_soft": "#382500",
    "marker": "#FFE27A",
    "page": "#080E1A",
    "surface": "#121928",
    "surface_soft": "#111F3D",
    "raised": "#1A2333",
    "ink": "#ECEEF4",
    "muted": "#A3ABBB",
    "line": "#283042",
    "line_strong": "#3C4558",
    "success": "#67C18F",
    "success_soft": "#002614",
    "danger": "#FF7E79",
    "danger_soft": "#410004",
    "hero": "#172B58",
}

FONTS = {
    "sans": '"Geologica", "Segoe UI", Arial, sans-serif',   # asosiy shrift
    "google_fonts_url": "https://fonts.googleapis.com/css2?family=Geologica:wght@400;500;600;700;800&display=swap",
}

RADIUS = {"sm": "8px", "md": "12px", "lg": "16px", "xl": "24px", "full": "9999px"}

FONT_SIZES = {"caption": "12px", "body_sm": "14px", "body": "16px", "title": "17px",
              "page_title": "20px", "title_lg": "24px", "display": "36px"}
