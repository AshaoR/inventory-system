"""
清理测试数据脚本。
只删除名称包含 "测试" 标记的物料及其关联数据。
安全模式：先预览再删除。
"""
import sys
from app import create_app
from app import db
from app.models import Material, Inventory, Transaction, InitialStock, Stocktake, StocktakeItem
from app.models import ImportPendingItem, SalesImportMapping, ImportLog

app = create_app()

TEST_MARKERS = ["测试"]  # 物料名称包含这些关键词即视为测试数据


def collect_test_material_ids():
    """查找所有带测试标记的物料 ID"""
    q = Material.query.filter(
        db.or_(Material.name.contains(m) for m in TEST_MARKERS)
    )
    materials = q.all()
    ids = [m.id for m in materials]
    return ids, materials


def preview():
    print("=" * 60)
    print("测试数据预览")
    print("=" * 60)
    mid_list, materials = collect_test_material_ids()
    mset = set(mid_list)

    if not materials:
        print("\n没有找到任何测试数据。")
        return 0

    print(f"\n物料 ({len(materials)} 条):")
    for m in materials:
        print(f"   [{m.code}] {m.name} ({m.spec or '-'}) - {m.warehouse_type}")

    # 关联数据计数
    inv_count = Inventory.query.filter(Inventory.material_id.in_(mset)).count()
    tx_count = Transaction.query.filter(Transaction.material_id.in_(mset)).count()
    is_count = InitialStock.query.filter(InitialStock.material_id.in_(mset)).count()
    si_count = StocktakeItem.query.filter(StocktakeItem.material_id.in_(mset)).count()

    if inv_count:
        print(f"  库存记录: {inv_count} 条")
    if tx_count:
        print(f"  出入库流水: {tx_count} 条")
    if is_count:
        print(f"  期初记录: {is_count} 条")
    if si_count:
        print(f"  盘点明细: {si_count} 条")

    # 查没有物料的盘点单/导入记录
    orphan_stocktakes = 0
    st_ids = set()
    for si in StocktakeItem.query.filter(StocktakeItem.material_id.in_(mset)).all():
        st_ids.add(si.stocktake_id)
    for st in Stocktake.query.filter(Stocktake.id.in_(st_ids)).all():
        all_test = StocktakeItem.query.filter(
            StocktakeItem.stocktake_id == st.id,
            ~StocktakeItem.material_id.in_(mset)
        ).count() == 0
        if all_test:
            orphan_stocktakes += 1

    total = (len(materials) + inv_count + tx_count + is_count + si_count + orphan_stocktakes)
    print(f"\n总计将删除约 {total} 条记录")
    return total


def do_delete(dry_run=True):
    mid_list, materials = collect_test_material_ids()
    if not materials:
        print("没有测试数据需要清理。")
        return

    mset = set(mid_list)
    print(f"\n正在{'预览' if dry_run else '删除'}...")

    tables = [
        ("盘点明细", StocktakeItem, lambda: StocktakeItem.query.filter(StocktakeItem.material_id.in_(mset))),
        ("出入库流水", Transaction, lambda: Transaction.query.filter(Transaction.material_id.in_(mset))),
        ("期初库存", InitialStock, lambda: InitialStock.query.filter(InitialStock.material_id.in_(mset))),
        ("库存记录", Inventory, lambda: Inventory.query.filter(Inventory.material_id.in_(mset))),
    ]

    for label, model, query_fn in tables:
        items = query_fn().all()
        if items:
            print(f"  {label}: {len(items)} 条")
            if not dry_run:
                for item in items:
                    db.session.delete(item)

    # 清理空盘点单
    st_ids = set()
    for si in StocktakeItem.query.filter(StocktakeItem.material_id.in_(mset)).all():
        st_ids.add(si.stocktake_id)
    for st_id in st_ids:
        other_items = StocktakeItem.query.filter(
            StocktakeItem.stocktake_id == st_id,
            ~StocktakeItem.material_id.in_(mset)
        ).count()
        if other_items == 0:
            st = Stocktake.query.get(st_id)
            if st:
                if not dry_run:
                    db.session.delete(st)
                print(f"  盘点单(空): #{st_id}")

    # 最后删物料
    for m in materials:
        print(f"  物料: [{m.code}] {m.name}")
        if not dry_run:
            db.session.delete(m)

    if dry_run:
        print("\n以上为将删除的数据。执行 python cleanup_data.py run 来实际删除。")
    else:
        db.session.commit()
        print(f"已删除 {len(materials)} 条物料及其关联数据。")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "preview"
    with app.app_context():
        if mode == "run":
            total = preview()
            if total > 0:
                confirm = input(f"\n确认删除以上 {total} 条测试数据？(yes/no): ")
                if confirm.strip().lower() == "yes":
                    do_delete(dry_run=False)
                else:
                    print("已取消。")
            else:
                do_delete(dry_run=False)
        elif mode == "preview":
            preview()
            do_delete(dry_run=True)
        else:
            print("用法: python cleanup_data.py [preview|run]")
            print("  preview  - 预览测试数据（默认）")
            print("  run      - 确认并删除测试数据")
