from sqlalchemy import Column, Integer, String
from database import Base


class Certificates(Base):
    __tablename__ = "certificates"

    cert_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    common_name = Column(String)
    not_before = Column(String)
    not_after = Column(String)
    cert_status = Column(String)
