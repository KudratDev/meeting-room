import psycopg2
import psycopg2.extras
from datetime import datetime
import uuid
from config import DATABASE_URL


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bookings (
                    id VARCHAR(8) PRIMARY KEY,
                    date VARCHAR(10) NOT NULL,
                    time_start VARCHAR(5) NOT NULL,
                    time_end VARCHAR(5) NOT NULL,
                    user_id VARCHAR(50) NOT NULL,
                    username VARCHAR(255),
                    comment TEXT DEFAULT ''
                )
            """)


def get_all_records():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, date, time_start, time_end, user_id, username, comment FROM bookings")
            return [dict(r) for r in cur.fetchall()]


def add_booking(date, time_start, time_end, user_id, username, comment=""):
    booking_id = str(uuid.uuid4())[:8].upper()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO bookings (id, date, time_start, time_end, user_id, username, comment) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (booking_id, date, time_start, time_end, str(user_id), username, comment)
            )
    return booking_id


def get_user_bookings(user_id):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, date, time_start, time_end, user_id, username, comment FROM bookings WHERE user_id = %s",
                (str(user_id),)
            )
            return [dict(r) for r in cur.fetchall()]


def get_bookings_by_date(date):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, date, time_start, time_end, user_id, username, comment FROM bookings WHERE date = %s",
                (date,)
            )
            return [dict(r) for r in cur.fetchall()]


def cancel_booking(booking_id, user_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bookings WHERE id = %s AND user_id = %s",
                (booking_id, str(user_id))
            )
            return cur.rowcount > 0


def is_time_available(date, time_start, time_end):
    bookings = get_bookings_by_date(date)
    new_start = datetime.strptime(time_start, "%H:%M")
    new_end = datetime.strptime(time_end, "%H:%M")
    for b in bookings:
        b_start = datetime.strptime(b["time_start"], "%H:%M")
        b_end = datetime.strptime(b["time_end"], "%H:%M")
        if not (new_end <= b_start or new_start >= b_end):
            return False
    return True


def get_booked_slots(date: str) -> list:
    bookings = get_bookings_by_date(date)
    busy = set()
    for b in bookings:
        start = time_to_minutes_storage(b["time_start"])
        end = time_to_minutes_storage(b["time_end"])
        t = start
        while t < end:
            busy.add(f"{t // 60:02d}:{t % 60:02d}")
            t += 30
    return list(busy)


def time_to_minutes_storage(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


init_db()
