# 库存管理系统 (KuCunManage)

紫洋玩具（毛绒玩具公司）专用库存管理系统，基于 Flask 开发。

## 功能模块

| 模块 | 说明 |
|------|------|
| **物料管理** | 原材料/半成品/成品物料的新增、编辑、停用/启用，支持批量创建 |
| **入库管理** | 采购入库、生产入库等，记录入库流水 |
| **出库管理** | 生产领用、销售出库等，支持强制出库 |
| **期初库存** | 初始化各仓库物料期初数量，自动累加至库存 |
| **库存查询** | 实时库存查看，物料流水追溯 |
| **盘点管理** | 创建盘点单，录入实盘数量，自动生成盘盈盘亏 |
| **导入管理** | 从秒账导出 Excel 导入销售数据，支持字段映射和预览确认 |

## 仓库类型

- **原材料仓**（raw）— 布料、填充棉、配件等
- **半成品仓**（semi）— 皮壳、未组装部件等
- **成品仓**（finished）— 最终成品

## 技术栈

- **后端**: Flask 3.1 + SQLAlchemy 2.0 + Flask-Login
- **前端**: Bootstrap 5.3 + Jinja2 + 金蝶风格 CSS
- **数据库**: SQLite（WAL 模式）
- **时区**: 北京时间（UTC+8）

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 初始化数据库
flask shell
>>> from app import db
>>> db.create_all()
>>> exit()

# 启动
python run.py
```

默认访问 http://localhost:5000

## 管理员账户

首次启动后通过 `/auth/register` 注册，或直接在数据库中创建。

## 项目结构

```
KuCunManage/
├── app/
│   ├── routes/          # 路由模块
│   ├── templates/       # Jinja2 模板
│   ├── static/          # CSS/JS 静态文件
│   ├── models.py        # 数据库模型
│   ├── services.py      # 业务逻辑层
│   ├── forms.py         # WTForms 表单
│   └── decorators.py    # 权限装饰器
├── config.py            # 应用配置
├── run.py               # 启动入口
├── requirements.txt     # 依赖清单
└── migrate_v2.py        # 数据库迁移脚本
```
