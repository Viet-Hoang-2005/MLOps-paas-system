# clear_production_data.py: Script xóa toàn bộ dữ liệu Production Data
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# 1. CẤU HÌNH TỪ BIẾN MÔI TRƯỜNG
# Load biến môi trường từ file .env khi chạy local
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(dotenv_path=os.path.join(ROOT_DIR, ".env"))

DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
# Ưu tiên sử dụng DB_HOST_RW để đảm bảo kết nối vào node Primary có quyền ghi/xóa
DB_HOST = os.environ.get("DB_HOST_RW", "postgres")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "mlops_paas_db")
TARGET_TABLE = "mlops_paas_production_data"


def clear_production_data():
    db_url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    try:
        engine = create_engine(db_url, pool_pre_ping=True)
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"Connected to PostgreSQL at {DB_HOST}:{DB_PORT}/{DB_NAME}")
    except Exception as e:
        print(f"Cannot connect to PostgreSQL: {e}")
        sys.exit(1)

    print(f"Attempting to TRUNCATE table '{TARGET_TABLE}'...")

    try:
        with engine.begin() as conn:
            # Dùng TRUNCATE thay vì DELETE để xóa toàn bộ dữ liệu nhanh nhất và giải phóng dung lượng
            conn.execute(text(f'TRUNCATE TABLE "{TARGET_TABLE}" RESTART IDENTITY;'))
        print(f"SUCCESS: All data in '{TARGET_TABLE}' has been cleared!")
    except Exception as e:
        print(
            f"ERROR: Failed to clear data. The table might not exist yet.\nDetail: {e}"
        )
        sys.exit(1)


if __name__ == "__main__":
    confirm = input(
        f"WARNING: This will permanently delete ALL data in '{TARGET_TABLE}'. Are you sure? (y/n): "
    )
    if confirm.lower() == "y":
        clear_production_data()
    else:
        print("Operation cancelled.")
