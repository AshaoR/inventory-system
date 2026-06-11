"""
数据库自动备份脚本
用法：python backup.py
建议通过 Windows 任务计划程序每天凌晨运行

设置任务计划时，"起始于(可选)" 必须填写项目绝对路径，如：
  D:\KuCunManage\
"""
import os
import shutil
import sys
from datetime import datetime, timedelta

# 获取脚本所在目录（不论从哪个目录调用都能正确工作）
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_FILE = os.path.join(BASE_DIR, "instance", "stock.db")
BACKUP_DIR = os.path.join(BASE_DIR, "backup")
RETENTION_DAYS = 30


def backup():
    # Ensure backup directory exists
    os.makedirs(BACKUP_DIR, exist_ok=True)

    if not os.path.exists(DB_FILE):
        print(f"错误：数据库文件不存在 - {DB_FILE}")
        return False

    today = datetime.now().strftime("%Y-%m-%d")
    backup_file = os.path.join(BACKUP_DIR, f"stock_{today}.db")

    if os.path.exists(backup_file):
        print(f"跳过：今日备份已存在 - {backup_file}")
    else:
        shutil.copy2(DB_FILE, backup_file)
        print(f"备份成功：{backup_file}")

    # Clean old backups (older than RETENTION_DAYS)
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    cleaned = 0
    for f in os.listdir(BACKUP_DIR):
        if f.startswith("stock_") and f.endswith(".db"):
            fpath = os.path.join(BACKUP_DIR, f)
            try:
                file_time = datetime.strptime(f.replace("stock_", "").replace(".db", ""), "%Y-%m-%d")
                if file_time < cutoff:
                    os.remove(fpath)
                    cleaned += 1
                    print(f"清理旧备份：{f}")
            except ValueError:
                continue

    if cleaned:
        print(f"已清理 {cleaned} 个旧备份文件")
    else:
        print("无需清理")

    return True


if __name__ == "__main__":
    success = backup()
    sys.exit(0 if success else 1)
