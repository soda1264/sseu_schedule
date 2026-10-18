from datetime import datetime, timedelta, timezone
import os
import sys
from icalendar import Calendar, Event
import requests

API_URL = "https://brso.sseu.ru/api/v1/schedule-board-user/by-student"

# Забираем секреты из переменных окружения
STUDENT_ID = os.environ.get("STUDENT_ID", "15651")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN")

if not AUTH_TOKEN:
  print(
      "Ошибка: не найдена переменная окружения AUTH_TOKEN. Добавь её в секреты"
      " GitHub или задай локально."
  )
  sys.exit(1)

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "authorization": AUTH_TOKEN,
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
    ),
}

# Отключаем системный прокси, чтобы не ловить ошибки с SOCKS
PROXIES = {"http": None, "https": None}

SAMARA_TZ = timezone(timedelta(hours=4))


def fetch_week(week_type="CURRENT"):
  today_str = datetime.now(SAMARA_TZ).strftime("%Y-%m-%d")
  params = {
      "studentId": STUDENT_ID,
      "scheduleWeek": week_type,
      "date": today_str,
  }
  try:
    response = requests.get(
        API_URL, headers=HEADERS, params=params, proxies=PROXIES, timeout=15
    )
    if response.status_code == 200:
      return response.json()
    print(f"Сервер вернул код {response.status_code} для недели {week_type}")
  except Exception as e:
    print(f"Ошибка сетевого запроса: {e}")
  return None


def extract_lessons(data):
  lessons = []
  if not data or not isinstance(data, dict):
    return lessons
  for key, value in data.items():
    if isinstance(value, dict) and "lessons" in value:
      lessons.extend(value["lessons"])
    elif key == "lessons" and isinstance(value, list):
      lessons.extend(value)
  return lessons


def create_ics(lessons, filename="schedule.ics"):
  cal = Calendar()
  cal.add("prodid", "-//SGEU Schedule Sync//ru")
  cal.add("version", "2.0")
  cal.add("x-wr-calname", "Расписание СГЭУ")
  cal.add("x-wr-timezone", "Europe/Samara")

  for lesson in lessons:
    lesson_date = lesson.get("date")
    number_data = lesson.get("lessonNumber") or {}
    start_time = number_data.get("timeStart")
    end_time = number_data.get("timeEnd")

    if not (lesson_date and start_time and end_time):
      continue

    dt_start = datetime.strptime(
        f"{lesson_date} {start_time}", "%Y-%m-%d %H:%M:%S"
    ).replace(tzinfo=SAMARA_TZ)
    dt_end = datetime.strptime(
        f"{lesson_date} {end_time}", "%Y-%m-%d %H:%M:%S"
    ).replace(tzinfo=SAMARA_TZ)

    work_plan = lesson.get("workPlan") or {}
    discipline = (work_plan.get("discipline") or {}).get(
        "name", "Учебное занятие"
    )
    lesson_type = (work_plan.get("lessonTypes") or {}).get("name", "")
    title = f"{discipline} ({lesson_type})" if lesson_type else discipline

    audiences = lesson.get("audiences") or []
    if audiences:
      aud = audiences[0]
      room = aud.get("name", "")
      location = f"Ауд. {room}".strip() if room else "Аудитория не указана"
    else:
      location = "Аудитория не указана"

    if lesson.get("replacementTeacher"):
      rep = lesson["replacementTeacher"]
      teacher = (
          f"Замена: {rep.get('fio', rep) if isinstance(rep, dict) else rep}"
      )
    elif lesson.get("teachers"):
      teacher = lesson["teachers"][0].get("fio") or lesson["teachers"][0].get(
          "teacher", "Не указан"
      )
    else:
      teacher = "Не указан"

    desc = (
        f"Пара №{number_data.get('number', '-')}\n"
        f"Тип: {lesson_type}\n"
        f"Преподаватель: {teacher}\n"
        f"Аудитория: {location}"
    )

    event = Event()
    event.add("summary", title)
    event.add("dtstart", dt_start.astimezone(timezone.utc))
    event.add("dtend", dt_end.astimezone(timezone.utc))
    event.add("location", location)
    event.add("description", desc)
    event.add(
        "uid", f"sgeu-{lesson.get('id', f'{lesson_date}-{start_time}')}@sseu.ru"
    )
    event.add("dtstamp", datetime.now(timezone.utc))

    cal.add_component(event)

  with open(filename, "wb") as f:
    f.write(cal.to_ical())


if __name__ == "__main__":
  records = []
  for week in ("CURRENT", "NEXT"):
    payload = fetch_week(week)
    records.extend(extract_lessons(payload))

  unique_lessons = {item["id"]: item for item in records if "id" in item}
  create_ics(unique_lessons.values())
  print("Файл schedule.ics сформирован.")
