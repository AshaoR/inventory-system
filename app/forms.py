from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SelectField, FloatField,
    DecimalField, TextAreaField, BooleanField, FileField,
)
from wtforms.validators import DataRequired, Optional, Length, NumberRange


class LoginForm(FlaskForm):
    username = StringField("用户名", validators=[DataRequired()])
    password = PasswordField("密码", validators=[DataRequired()])


class MaterialForm(FlaskForm):
    name = StringField("物料名称", validators=[DataRequired(), Length(max=200)])
    spec = StringField("规格型号", validators=[Optional(), Length(max=200)])
    unit = SelectField(
        "单位",
        choices=[
            ("个", "个"), ("只", "只"), ("米", "米"), ("千克", "千克"),
            ("包", "包"), ("箱", "箱"), ("套", "套"), ("张", "张"),
            ("卷", "卷"), ("条", "条"),
        ],
        default="个",
    )
    warehouse_type = SelectField(
        "所属仓库",
        choices=[("raw", "原材料仓"), ("semi", "半成品仓"), ("finished", "成品仓")],
        validators=[DataRequired()],
    )
    category = SelectField(
        "物料分类",
        choices=[
            ("", "请选择"), ("面料", "面料"), ("填充棉", "填充棉"),
            ("配件", "配件"), ("包装", "包装"), ("衣服", "衣服"),
            ("其他", "其他"),
        ],
        default="",
    )
    min_stock = FloatField("最低库存预警", default=0, validators=[Optional()])


class StocktakeForm(FlaskForm):
    warehouse_id = SelectField("盘点仓库", coerce=int, validators=[DataRequired()])
    remark = TextAreaField("备注", validators=[Optional(), Length(max=500)])


class ImportUploadForm(FlaskForm):
    file = FileField("选择Excel文件", validators=[DataRequired()])


class MappingForm(FlaskForm):
    external_name = StringField("外部产品名称", validators=[DataRequired(), Length(max=200)])
    material_id = SelectField("对应物料", coerce=int, validators=[DataRequired()])
