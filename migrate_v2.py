"""数据库迁移脚本：为 v2 优化添加新字段和索引

迁移内容：
1. transactions 表添加 initial_stock_id 字段（关联 initial_stock）
2. import_logs.file_hash 添加唯一索引
3. 添加高频查询字段的索引
4. 回填已有期初库存记录的 initial_stock_id
"""
import sqlite3
import os

basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, "instance", "stock.db")

if not os.path.exists(db_path):
    print(f"未找到数据库文件：{db_path}")
    exit(0)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()


def check_column_exists(table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(col[1] == column for col in cursor.fetchall())


def check_index_exists(index_name):
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name=?", (index_name,))
    return cursor.fetchone() is not None


print("=" * 60)
print("[迁移开始]")
print("=" * 60)

# 1. transactions 表添加 initial_stock_id
if not check_column_exists("transactions", "initial_stock_id"):
    print("[1/4] 添加 transactions.initial_stock_id 字段...")
    cursor.execute("ALTER TABLE transactions ADD COLUMN initial_stock_id INTEGER REFERENCES initial_stock(id)")
    print("  [OK]")
else:
    print("[1/4] transactions.initial_stock_id 已存在，跳过")

# 2. import_logs.file_hash 唯一索引
if not check_index_exists("ix_import_logs_file_hash"):
    print("[2/4] 创建 import_logs.file_hash 唯一索引...")
    # 先清理重复数据（保留最新的记录）
    cursor.execute("""
        DELETE FROM import_logs WHERE id NOT IN (
            SELECT MAX(id) FROM import_logs GROUP BY file_hash
        )
    """)
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_import_logs_file_hash ON import_logs(file_hash)")
    print("  [OK]")
else:
    print("[2/4] import_logs.file_hash 唯一索引已存在，跳过")

# 3. 高频查询索引
indexes = [
    ("ix_transaction_material_id", "transactions(material_id)"),
    ("ix_transaction_warehouse_id", "transactions(warehouse_id)"),
    ("ix_transaction_direction", "transactions(direction)"),
    ("ix_inventory_warehouse_id", "inventory(warehouse_id)"),
]

for idx_name, idx_def in indexes:
    if not check_index_exists(idx_name):
        print(f"[3/4] 创建索引 {idx_name}...")
        cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def}")
        print(f"  [OK]")
    else:
        print(f"[3/4] 索引 {idx_name} 已存在，跳过")

# 4. 回填已有期初库存记录的 initial_stock_id
print("[4/4] 回填 transactions.initial_stock_id...")
cursor.execute("""
    UPDATE transactions
    SET initial_stock_id = (
        SELECT initial_stock.id FROM initial_stock
        WHERE initial_stock.material_id = transactions.material_id
          AND initial_stock.warehouse_id = transactions.warehouse_id
          AND initial_stock.quantity = transactions.quantity
          AND initial_stock.created_at = transactions.created_at
        LIMIT 1
    )
    WHERE transactions.transaction_type = '期初录入'
      AND transactions.initial_stock_id IS NULL
""")
updated = cursor.rowcount
print(f"  [OK] 已回填 {updated} 条记录")

conn.commit()
conn.close()

print("=" * 60)
print("[迁移完成]")
print("=" * 60)
