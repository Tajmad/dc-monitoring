import os
import re
import subprocess
import sys
from datetime import datetime
import streamlit as st
from bs4 import BeautifulSoup


# ==================== ВНОСИМ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def parse_downtime_minutes(time_str):
    """Преобразует текстовое время простоя (напр. '4 hours 4 minutes 12 seconds') в минуты."""
    if not time_str or time_str == "—":
        return 0
    
    time_str = time_str.lower()
    total_mins = 0
    
    days_m = re.search(r"(\d+)\s*day", time_str)
    hours_m = re.search(r"(\d+)\s*hour", time_str)
    mins_m = re.search(r"(\d+)\s*min", time_str)
    
    if days_m:
        total_mins += int(days_m.group(1)) * 24 * 60
    if hours_m:
        total_mins += int(hours_m.group(1)) * 60
    if mins_m:
        total_mins += int(mins_m.group(1))
        
    return total_mins


def format_overdue(total_mins, allowed_hours):
    """Форматирует статус просрочки на основе допустимого лимита в часах."""
    allowed_mins = allowed_hours * 60
    if total_mins <= allowed_mins:
        remaining = allowed_mins - total_mins
        r_hrs = remaining // 60
        r_mins = remaining % 60
        if r_hrs > 0:
            return f"🟢 В норме (осталось {r_hrs} ч {r_mins} мин)"
        return f"🟢 В норме (осталось {r_mins} мин)"
    else:
        overdue = total_mins - allowed_mins
        o_hrs = overdue // 60
        o_mins = overdue % 60
        if o_hrs > 0:
            return f"🚨 Просрочено на {o_hrs} ч {o_mins} мин"
        return f"🚨 Просрочено на {o_mins} мин"


def parse_ezs_last_conn_mins(last_conn_str):
    """Парсит дату/время последнего подключения ЭЗС и считывает разницу в минутах."""
    if not last_conn_str or last_conn_str == "—":
        return 999999
    
    # Обработка формата относительного времени (напр. '2 hours ago', '45 mins ago')
    if "ago" in last_conn_str.lower() or "назад" in last_conn_str.lower():
        return parse_downtime_minutes(last_conn_str)
        
    # Обработка стандартного формата даты YYYY-MM-DD HH:MM:SS
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(last_conn_str.strip(), fmt)
            diff = datetime.now() - dt
            return int(diff.total_seconds() / 60)
        except Exception:
            pass
            
    return 0


# ==================== ИНИЦИАЛИЗАЦИЯ PLAYWRIGHT В ОБЛАКЕ ====================
@st.cache_resource
def init_playwright():
    """Автоматическая установка бинарников Chromium при старте приложения."""
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    except Exception as e:
        st.error(f"Ошибка при инициализации Playwright: {e}")

# Вызов инициализации
init_playwright()

from playwright.sync_api import sync_playwright

# Настройка путей только для скомпилированного .exe (локально)
if getattr(sys, "_MEIPASS", False):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(sys._MEIPASS, "ms-playwright")

# Общие флаги запуска браузера Chromium для облачной среды и Linux-контейнеров
BROWSER_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--single-process",
]

# Настройка страницы
st.set_page_config(
    page_title="Единый мониторинг DC", page_icon="⚡", layout="wide"
)

# ==================== БОКОВАЯ ПАНЕЛЬ (НАСТРОЙКИ) ====================
with st.sidebar:
    st.header("⚙️ Настройки")
    
    # Настройка порога простоя для парковок
    offline_threshold = st.number_input(
        "Минут простоя до Офлайна (Парковки):",
        min_value=1,
        max_value=1440,
        value=10,
        step=5,
        help="Если устройство не отправляет данные дольше указанного количества минут, оно считается аварийным."
    )

# ==================== ОСНОВНОЙ ЭКРАН ====================
st.title("⚡ Единая панель мониторинга (Парковки, ЭЗС, Шохин)")
st.write("Оперативный контроль состояния оборудования в реальном времени.")

# Создаем ТРИ вкладки
tab_parking, tab_ezs, tab_shohin = st.tabs(
    ["🅿️ Парковки DC", "⚡ ЭЗС (CityPower)", "📡 Шохин (Net Solutions)"]
)

# ==================== ВКЛАДКА 1: ПАРКОВКИ ====================
with tab_parking:
    if st.button("🔄 Запустить сканирование парковок", type="primary", key="btn_parking"):
        with st.spinner("Сканируем парковки... Подожди немного."):
            offline_stations = []
            offline_count = 0
            online_count = 0
            archive_count = 0
            total_stations = 0

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=BROWSER_LAUNCH_ARGS)
                page = browser.new_context().new_page()

                try:
                    page.goto("https://parking.dc.tj/login")
                    page.fill('input[name="Login"]', "Saidakbar")
                    page.fill('input[name="password"]', "said3344")
                    page.click('button[type="submit"]')
                    page.wait_for_timeout(2000)

                    for page_num in range(1, 16):
                        target_url = f"https://parking.dc.tj/device-states/index?page={page_num}"
                        page.goto(target_url)
                        page.wait_for_timeout(1500)

                        html_content = page.content()
                        soup = BeautifulSoup(html_content, "html.parser")
                        rows = soup.select("table tbody tr")

                        if not rows:
                            break

                        for row in rows:
                            cols = row.find_all("td")
                            if len(cols) < 7:
                                continue

                            total_stations += 1
                            station_id = cols[1].text.strip().split()[0]
                            try:
                                timeout_mins = int(cols[3].text.strip())
                            except Exception:
                                timeout_mins = 0

                            address = cols[7].text.strip() if len(cols) > 7 else ""
                            time_passed_raw = cols[5].text.strip().lower()

                            total_passed_mins = parse_downtime_minutes(time_passed_raw)

                            is_archive = False
                            is_offline = False

                            if (
                                "day" in time_passed_raw
                                or "month" in time_passed_raw
                                or "year" in time_passed_raw
                            ):
                                try:
                                    parts_days = time_passed_raw.split()
                                    days_val = int(parts_days[0])
                                    if (
                                        "week" in time_passed_raw
                                        or "month" in time_passed_raw
                                        or "year" in time_passed_raw
                                        or days_val >= 21
                                    ):
                                        is_archive = True
                                except Exception:
                                    pass

                            effective_limit = timeout_mins if timeout_mins > 0 else offline_threshold

                            if not is_archive:
                                if total_passed_mins > effective_limit:
                                    is_offline = True

                            if is_archive:
                                archive_count += 1
                            elif is_offline:
                                offline_count += 1
                                # Расчет просрочки ремонта (Лимит — 3 часа)
                                overdue_status = format_overdue(total_passed_mins, allowed_hours=3)
                                
                                offline_stations.append(
                                    {
                                        "ID станции": station_id,
                                        "Время простоя": time_passed_raw,
                                        "Просрочка (лимит 3 ч)": overdue_status,
                                        "Адрес": address if address else "Не указан",
                                    }
                                )
                            else:
                                online_count += 1
                finally:
                    browser.close()

            st.session_state["parking_data"] = {
                "total": total_stations,
                "online": online_count,
                "offline": offline_count,
                "archive": archive_count,
                "offline_list": offline_stations,
            }

    if "parking_data" in st.session_state:
        d = st.session_state["parking_data"]
        st.markdown("---")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Всего объектов", d["total"])
        col2.metric("Онлайн 🟢", d["online"])
        col3.metric("Офлайн (Авария) 🔴", d["offline"])
        col4.metric("Архив (> 3 недель) 📦", d["archive"])

        st.markdown("---")
        if d["offline_list"]:
            st.error(f"⚠️ Внимание! Обнаружено аварийных парковок: {len(d['offline_list'])}")
            st.dataframe(d["offline_list"], width="stretch")
        else:
            st.success("🎉 Все парковки на связи, аварий нет.")


# ==================== ВКЛАДКА 2: ЭЗС (CITYPOWER) ====================
with tab_ezs:
    if st.button("🔄 Запустить сканирование ЭЗС", type="primary", key="btn_ezs"):
        with st.spinner("Авторизуемся в CityPower, собираем офлайн-станции..."):
            ezs_offline_list = []

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=BROWSER_LAUNCH_ARGS)
                page = browser.new_context().new_page()

                try:
                    page.goto("https://citypower.dc.tj/admin_panel/home")
                    page.wait_for_timeout(2000)

                    try:
                        if page.locator('input[name="email"], input[type="email"]').count() > 0:
                            page.fill('input[name="email"], input[type="email"]', "navruz65@mail.ru")
                            page.fill('input[name="password"], input[type="password"]', "d)sX@&")
                            page.click(
                                'button[type="submit"], input[type="submit"], button:has-text("Login")'
                            )
                            page.wait_for_timeout(3000)
                    except Exception:
                        pass

                    page.goto("https://citypower.dc.tj/admin_panel/station?status=offline")
                    page.wait_for_timeout(3000)

                    try:
                        page.select_option("select", "100")
                        page.wait_for_timeout(2000)
                    except Exception:
                        try:
                            page.select_option('select[class*="form-control"]', "100")
                            page.wait_for_timeout(2000)
                        except Exception:
                            pass

                    html_content = page.content()
                    soup = BeautifulSoup(html_content, "html.parser")
                    rows = soup.select("table tbody tr")

                    if rows:
                        for row in rows:
                            cols = row.find_all("td")
                            if len(cols) < 7:
                                continue

                            station_id = cols[1].text.strip()
                            address = cols[2].text.strip()
                            status = cols[3].text.strip()
                            error_reason = cols[5].text.strip() if cols[5].text.strip() else "—"
                            last_conn = cols[6].text.strip()

                            # Расчет просрочки восстановления (Лимит — 1 час)
                            last_conn_mins = parse_ezs_last_conn_mins(last_conn)
                            overdue_status = format_overdue(last_conn_mins, allowed_hours=1)

                            ezs_offline_list.append(
                                {
                                    "ID станции": station_id,
                                    "Адрес": address,
                                    "Статус": status,
                                    "Причина неисправности": error_reason,
                                    "Последнее подключение": last_conn,
                                    "Просрочка (лимит 1 ч)": overdue_status,
                                }
                            )
                finally:
                    browser.close()

            st.session_state["ezs_data"] = {"offline_list": ezs_offline_list}

    if "ezs_data" in st.session_state:
        e = st.session_state["ezs_data"]
        st.markdown("---")
        st.metric("Офлайн ЭЗС (Авария) 🔴", len(e["offline_list"]))

        st.markdown("---")
        if e["offline_list"]:
            st.error(f"⚠️ Внимание! Обнаружено проблемных ЭЗС: {len(e['offline_list'])}")
            st.dataframe(e["offline_list"], width="stretch")
        else:
            st.success("🎉 Все электрозаправки работают штатно, аварий нет.")


# ==================== ВКЛАДКА 3: ШОХИН ====================
with tab_shohin:
    if st.button("🔄 Запустить сканирование Шохин", type="primary", key="btn_shohin_final_all"):
        with st.spinner("Сканируем устройства и собираем данные..."):
            shohin_offline_list = []
            shohin_metrics = {"total_all": 0, "radar_offline": 0, "chorroha_offline": 0}

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=BROWSER_LAUNCH_ARGS)
                context = browser.new_context(viewport={"width": 1920, "height": 1080})
                page = context.new_page()

                try:
                    page.goto("http://10.251.6.239/sign-in", timeout=60000)
                    page.wait_for_timeout(1000)
                    if page.locator('input[type="text"], input[name="username"]').count() > 0:
                        page.fill('input[type="text"], input[name="username"]', "akbar8976")
                        page.fill('input[type="password"]', "akbar8976")
                        page.locator(
                            'button[type="submit"], button:has-text("Войти")'
                        ).first.click()
                        page.wait_for_timeout(2000)

                    page.goto("http://10.251.6.239/devices", timeout=60000)
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(3000)

                    if page.locator('text="Net Solutions"').count() > 0:
                        page.locator('text="Net Solutions"').first.click()
                        page.wait_for_timeout(2000)

                    if page.locator('button:has-text("Подробно")').count() > 0:
                        page.locator('button:has-text("Подробно")').click()
                        page.wait_for_timeout(3000)

                    page_text = page.locator("body").inner_text()
                    radar_m = re.search(r"Радар\s+(\d+)/(\d+)", page_text, re.IGNORECASE)
                    chorroha_m = re.search(r"Чорроха.*?\s+(\d+)/(\d+)", page_text, re.IGNORECASE)
                    total_m = re.search(r"Всего\s+(\d+)/(\d+)", page_text, re.IGNORECASE)

                    if radar_m:
                        shohin_metrics["radar_offline"] = int(radar_m.group(1))
                    if chorroha_m:
                        shohin_metrics["chorroha_offline"] = int(chorroha_m.group(1))
                    if total_m:
                        shohin_metrics["total_all"] = int(total_m.group(1))

                    seen_ips = {}

                    for page_num in range(3):
                        table_rows = page.evaluate(r"""
                          () => {
                            const rows = [];
                            const allEls = document.querySelectorAll('*');
                            allEls.forEach(el => {
                              const text = el.innerText || '';
                              if (text.includes('10.251.') || text.includes('10.248.')) {
                                if (text.includes('LK')) {
                                  rows.push({
                                    html: el.outerHTML,
                                    text: text.trim()
                                  });
                                }
                              }
                            });
                            return rows;
                          }
                        """)

                        for r in table_rows:
                            txt = r["text"]
                            html = r["html"].lower()

                            ip_m = re.search(r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}", txt)
                            name_m = re.search(r"LK[-/][A-Za-z0-9\-]+", txt)

                            if ip_m and name_m:
                                ip = ip_m.group(0)
                                name = name_m.group(0).split("\n")[0].strip()

                                status = None
                                if any(
                                    c in html
                                    for c in [
                                        "red",
                                        "danger",
                                        "offline",
                                        "255, 59, 48",
                                        "244, 67, 54",
                                        "#ff3b30",
                                    ]
                                ):
                                    status = "Офлайн 🔴"
                                elif any(
                                    c in html
                                    for c in [
                                        "orange",
                                        "warning",
                                        "255, 149, 0",
                                        "255, 152, 0",
                                        "#ff9500",
                                    ]
                                ):
                                    status = "Предупреждение 🟠"

                                if status and ip not in seen_ips:
                                    category = (
                                        "Чорроха (Linux)"
                                        if ("LK/Q" in name or "10.251." in ip)
                                        else "Радар"
                                    )
                                    seen_ips[ip] = {
                                        "Имя устройства": name,
                                        "IP-адрес": ip,
                                        "Категория": category,
                                        "Статус": status,
                                        "Лимит восстановления": "3 часа (Норма)",
                                    }

                        next_btn = page.locator(
                            'button:has(.q-icon:has-text("chevron_right")), button.q-pagination__next, [aria-label="Next page"], button:has-text(">")'
                        ).first
                        if next_btn.count() > 0 and next_btn.is_visible():
                            try:
                                next_btn.click()
                                page.wait_for_timeout(1000)
                            except Exception:
                                break
                        else:
                            break

                    shohin_offline_list = list(seen_ips.values())

                except Exception as e:
                    st.error(f"Ошибка: {e}")
                finally:
                    browser.close()

            st.session_state["shohin_data"] = {
                "offline_list": shohin_offline_list,
                "metrics": shohin_metrics,
            }

    # Отрисовка результатов
    if "shohin_data" in st.session_state:
        s = st.session_state["shohin_data"]
        m = s["metrics"]
        st.markdown("---")

        col1, col2, col3 = st.columns(3)
        col1.metric("Всего устройств", f"{m['total_all']}")
        total_problems = m["radar_offline"] + m["chorroha_offline"]
        col2.metric("Всего проблемных (По сводке)", f"{total_problems}")
        col3.metric(
            "Радар / Чорроха (Проблем)", f"{m['radar_offline']} / {m['chorroha_offline']}"
        )

        st.markdown("---")
        parsed_count = len(s["offline_list"])

        if parsed_count >= total_problems:
            st.success(
                f"✅ Успешно собраны все проблемные устройства: {parsed_count} из {total_problems}!"
            )
        else:
            st.warning(f"⚠️ Собрано устройств: {parsed_count} из {total_problems}.")

        st.dataframe(s["offline_list"], width="stretch")