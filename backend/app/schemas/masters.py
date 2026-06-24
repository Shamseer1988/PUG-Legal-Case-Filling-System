"""Master data schemas."""

from pydantic import BaseModel, ConfigDict, Field


# ---------- Division ----------
class DivisionBase(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=200)
    address: str = ""
    accountant_email: str = ""
    manager_email: str = ""
    sales_manager_email: str = ""
    is_active: bool = True


class DivisionCreate(DivisionBase):
    pass


class DivisionUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    address: str | None = None
    accountant_email: str | None = None
    manager_email: str | None = None
    sales_manager_email: str | None = None
    is_active: bool | None = None


class DivisionRead(DivisionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ---------- Bank ----------
class BankBase(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=200)
    is_active: bool = True


class BankCreate(BankBase):
    pass


class BankUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    is_active: bool | None = None


class BankRead(BankBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ---------- Salesman ----------
class SalesmanBase(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=200)
    email: str = ""
    phone: str = ""
    division_id: int | None = None
    is_active: bool = True


class SalesmanCreate(SalesmanBase):
    pass


class SalesmanUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    division_id: int | None = None
    is_active: bool | None = None


class SalesmanRead(SalesmanBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ---------- Customer ----------
class CustomerBase(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=200)
    customer_type: str = "Retail"
    phone: str = ""
    email: str = ""
    address: str = ""
    division_id: int | None = None
    salesman_id: int | None = None
    is_active: bool = True


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    customer_type: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    division_id: int | None = None
    salesman_id: int | None = None
    is_active: bool | None = None


class CustomerRead(CustomerBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ---------- Lawyer ----------
class LawyerBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    firm: str = ""
    email: str = ""
    phone: str = ""
    is_active: bool = True
    is_all_divisions: bool = False


class LawyerCreate(LawyerBase):
    division_ids: list[int] = Field(default_factory=list)


class LawyerUpdate(BaseModel):
    name: str | None = None
    firm: str | None = None
    email: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    is_all_divisions: bool | None = None
    division_ids: list[int] | None = None


class LawyerRead(LawyerBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    division_ids: list[int] = Field(default_factory=list)


# ---------- Case Type ----------
class CaseTypeBase(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    is_active: bool = True


class CaseTypeCreate(CaseTypeBase):
    pass


class CaseTypeUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class CaseTypeRead(CaseTypeBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
