from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import Product, ProductLine, UserPermissionGrant, UserProductLine
from tests.conftest import make_user


def test_product_line_name_property(db):
    line = ProductLine(name="扫地机")
    db.add(line)
    db.flush()
    product = Product(name="扫地机器人", model="X1", line_id=line.id)
    db.add(product)
    db.commit()

    assert product.line.name == "扫地机"
    assert product.line_name == "扫地机"


def test_user_product_line_and_grant_rows(db):
    user = make_user(db)
    line = ProductLine(name="净化器")
    db.add(line)
    db.flush()
    db.add(UserProductLine(user_id=user.id, line_id=line.id))
    db.add(
        UserPermissionGrant(
            user_id=user.id,
            permission="fault:write",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            reason="临时接手知识库",
        )
    )
    db.commit()

    assert db.scalar(select(UserProductLine).where(UserProductLine.user_id == user.id)) is not None
    assert db.scalar(select(UserPermissionGrant).where(UserPermissionGrant.user_id == user.id)) is not None
