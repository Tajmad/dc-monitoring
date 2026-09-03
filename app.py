from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import streamlit as st
import os
import sys
import subprocess
import re

# Автоматическая установка браузера Playwright для облака Streamlit
try:
  subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
except Exception:
  pass

# Настройка путей для Playwright внутри скомпилированного .exe (если запускается локально)
if hasattr(sys, '_MEIPASS'):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(sys._MEIPASS, "ms-playwright")
else:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(current_dir, "ms-playwright")

# Настройка страницы браузера
st.set_page_config(
    page_title="Единый мониторинг DC", page_icon="⚡", layout="wide"
)

# ==================== БОКОВАЯ ПАНЕЛЬ (УПРАВЛЕНИЕ) ====================
with st.sidebar:
    st.header("⚙️ Управление")
    st.write("Панель контроля приложением.")
    
    if st.button("🛑 Выключить приложение", type="secondary", key="btn_shutdown"):
        st.warning("Сервер останавливается...")
        os._exit(0) # Полностью завершает процесс python / .exe

# ==================== ОСНОВНОЙ ЭКРАН ====================
st.title("⚡ Единая панель мониторинга (Парковки, ЭЗС, Шохин)")
st.write("Оперативный контроль состояния оборудования в реальном времени.")

# Создаем ТРИ вкладки
tab_parking, tab_ezs, tab_shohin = st.tabs(["🅿️ Парковки DC", "⚡ ЭЗС (CityPower)", "📡 Шохин (Net Solutions)"])

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
        browser = p.chromium.launch(headless=True)
        page = browser.new_context().new_page()

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
            except:
              timeout_mins = 0

            address = cols[7].text.strip() if len(cols) > 7 else ""
            time_passed_raw = cols[5].text.strip().lower()

            total_passed_mins = 0
            try:
              parts = time_passed_raw.split()
              val = int(parts[0])
              unit = parts[1]

              if "sec" in unit:
                total_passed_mins = 0.5
              elif "min" in unit:
                total_passed_mins = val
              elif "hour" in unit:
                total_passed_mins = val * 60
              elif "day" in unit:
                total_passed_mins = val * 24 * 60
            except:
              total_passed_mins = 999999

            is_archive = False
            is_offline = False

            if "day" in time_passed_raw or "month" in time_passed_raw or "year" in time_passed_raw:
              try:
                parts_days = time_passed_raw.split()
                days_val = int(parts_days[0])
                if "week" in time_passed_raw or "month" in time_passed_raw or "year" in time_passed_raw or days_val >= 21:
                  is_archive = True
              except:
                pass

            if not is_archive:
              if (timeout_mins > 0 and total_passed_mins > timeout_mins) or (total_passed_mins > 10):
                is_offline = True

            if is_archive:
              archive_count += 1
            elif is_offline:
              offline_count += 1
              offline_stations.append({
                  "ID станции": station_id,
                  "Камера / Время простоя": time_passed_raw,
                  "Лимит (мин)": timeout_mins,
                  "Адрес": address if address else "Не указан",
              })
            else:
              online_count += 1

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
      st.dataframe(d["offline_list"], width='stretch')
    else:
      st.success("🎉 Все парковки на связи, аварий нет.")


# ==================== ВКЛАДКА 2: ЭЗС (CITYPOWER) ====================
with tab_ezs:
  if st.button("🔄 Запустить сканирование ЭЗС", type="primary", key="btn_ezs"):
    with st.spinner("Авторизуемся в CityPower, собираем офлайн-станции..."):
      ezs_offline_list = []

      with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context().new_page()

        page.goto("https://citypower.dc.tj/admin_panel/home")
        page.wait_for_timeout(2000)

        try:
          if page.locator('input[name="email"], input[type="email"]').count() > 0:
            page.fill('input[name="email"], input[type="email"]', "navruz65@mail.ru")
            page.fill('input[name="password"], input[type="password"]', "d)sX@&")
            page.click('button[type="submit"], input[type="submit"], button:has-text("Login")')
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

            ezs_offline_list.append({
                "ID станции": station_id,
                "Адрес": address,
                "Статус": status,
                "Причина неисправности": error_reason,
                "Последнее подключение": last_conn,
            })

        browser.close()

      st.session_state["ezs_data"] = {"offline_list": ezs_offline_list}

  if "ezs_data" in st.session_state:
    e = st.session_state["ezs_data"]
    st.markdown("---")
    st.metric("Офлайн ЭЗС (Авария) 🔴", len(e["offline_list"]))

    st.markdown("---")
    if e["offline_list"]:
      st.error(f"⚠️ Внимание! Обнаружено проблемных ЭЗС: {len(e['offline_list'])}")
      st.dataframe(e["offline_list"], width='stretch')
    else:
      st.success("🎉 Все электрозаправки работают штатно, аварий нет.")


# ==================== ВКЛАДКА 3: ШОХИН ====================
with tab_shohin:
  if st.button("🔄 Запустить сканирование Шохин", type="primary", key="btn_shohin_final_all"):
    with st.spinner("Сканируем устройства и собираем данные..."):
      shohin_offline_list = []
      shohin_metrics = {"total_all": 0, "radar_offline": 0, "chorroha_offline": 0}

      with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        try:
          page.goto("http://10.251.6.239/sign-in", timeout=60000)
          page.wait_for_timeout(1000)
          if page.locator('input[type="text"], input[name="username"]').count() > 0:
            page.fill('input[type="text"], input[name="username"]', "akbar8976")
            page.fill('input[type="password"]', "akbar8976")
            page.locator('button[type="submit"], button:has-text("Войти")').first.click()
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

          # Считываем общие метрики со страницы
          page_text = page.locator("body").inner_text()
          radar_m = re.search(r"Радар\s+(\d+)/(\d+)", page_text, re.IGNORECASE)
          chorroha_m = re.search(r"Чорроха.*?\s+(\d+)/(\d+)", page_text, re.IGNORECASE)
          total_m = re.search(r"Всего\s+(\d+)/(\d+)", page_text, re.IGNORECASE)

          if radar_m: shohin_metrics["radar_offline"] = int(radar_m.group(1))
          if chorroha_m: shohin_metrics["chorroha_offline"] = int(chorroha_m.group(1))
          if total_m: shohin_metrics["total_all"] = int(total_m.group(1))

          seen_ips = {}
          
          # Цикл сбора с поддержкой страниц/скролла
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
                name = name_m.group(0).split('\n')[0].strip()

                status = None
                if any(c in html for c in ['red', 'danger', 'offline', '255, 59, 48', '244, 67, 54', '#ff3b30']):
                  status = "Офлайн 🔴"
                elif any(c in html for c in ['orange', 'warning', '255, 149, 0', '255, 152, 0', '#ff9500']):
                  status = "Предупреждение 🟠"
                
                if status and ip not in seen_ips:
                  category = "Чорроха (Linux)" if ("LK/Q" in name or "10.251." in ip) else "Радар"
                  seen_ips[ip] = {
                      "Имя устройства": name,
                      "IP-адрес": ip,
                      "Категория": category,
                      "Статус": status
                  }

            # Пробуем переключить страницу, если есть пагинация
            next_btn = page.locator('button:has(.q-icon:has-text("chevron_right")), button.q-pagination__next, [aria-label="Next page"], button:has-text(">")').first
            if next_btn.count() > 0 and next_btn.is_visible():
              try:
                next_btn.click()
                page.wait_for_timeout(1000)
              except:
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
          "metrics": shohin_metrics
      }

  # Отрисовка результатов
  if "shohin_data" in st.session_state:
    s = st.session_state["shohin_data"]
    m = s["metrics"]
    st.markdown("---")

    col1, col2, col3 = st.columns(3)
    col1.metric("Всего устройств", f"{m['total_all']}")
    total_problems = m['radar_offline'] + m['chorroha_offline']
    col2.metric("Всего проблемных (По сводке)", f"{total_problems}")
    col3.metric("Радар / Чорроха (Проблем)", f"{m['radar_offline']} / {m['chorroha_offline']}")

    st.markdown("---")
    parsed_count = len(s['offline_list'])
    
    if parsed_count >= total_problems:
      st.success(f"✅ Успешно собраны все проблемные устройства: {parsed_count} из {total_problems}!")
    else:
      st.warning(f"⚠️ Собрано устройств: {parsed_count} из {total_problems}.")

    st.dataframe(s["offline_list"], width='stretch')