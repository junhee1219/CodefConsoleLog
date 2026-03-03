from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ErrReport(Base):
    __tablename__ = "err_report"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="에러 고유 ID")
    log_id: Mapped[str | None] = mapped_column(String(64))
    reg_time: Mapped[datetime | None] = mapped_column(DateTime, comment="발생 시각")
    product_code: Mapped[str | None] = mapped_column(String(64), comment="상품 코드")
    product_name: Mapped[str | None] = mapped_column(String(128), comment="상품명")
    business_type: Mapped[str | None] = mapped_column(String(16), comment="업종 코드 (BK/CD/IS 등)")
    business_type_name: Mapped[str | None] = mapped_column(String(64), comment="업종명")
    product_info2: Mapped[str | None] = mapped_column(String(64))
    product_info3: Mapped[str | None] = mapped_column(String(64))
    err_type: Mapped[str | None] = mapped_column(String(8))
    err_code: Mapped[str | None] = mapped_column(String(32), comment="에러 코드")
    err_msg: Mapped[str | None] = mapped_column(String(512), comment="에러 메시지")

    # 상세 정보 (getErrDetail)
    detail_raw: Mapped[str | None] = mapped_column(Text, comment="상세 응답 원본 JSON")
    detail_extra_message: Mapped[str | None] = mapped_column(String(1024))
    detail_organization: Mapped[str | None] = mapped_column(String(32), comment="기관 코드")
    detail_connected_id: Mapped[str | None] = mapped_column(String(128))
    detail_err_cnt: Mapped[int | None] = mapped_column(Integer)
    detail_success_cnt: Mapped[int | None] = mapped_column(Integer)
    detail_req_cnt: Mapped[int | None] = mapped_column(Integer)

    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="수집 시각")

    __table_args__ = (
        Index("ix_err_report_reg_time", "reg_time"),
        Index("ix_err_report_err_code", "err_code"),
        Index("ix_err_report_product_code", "product_code"),
        Index("ix_err_report_business_type", "business_type"),
    )
