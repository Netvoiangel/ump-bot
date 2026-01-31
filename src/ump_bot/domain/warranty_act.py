from pydantic import BaseModel, Field
from datetime import date
from typing import Optional, List

class WarrantyActData(BaseModel):
    # Дата акта
    act_date: date = Field(default_factory=date.today)
    
    # Парк и адрес
    park_name: str
    address: str
    
    # Номер заявки
    request_no: str
    
    # Данные ТС
    license_plate: str # Госномер
    garage_no: str     # Гаражный номер
    
    # Описание работ
    reported_fault: str  # Заявленная неисправность
    diagnostic_result: str # Результат диагностики
    performed_works: str  # Выполненные работы
    
    # Исполнитель
    executor_name: str
    
    # Даты предоставления и окончания (в ТЗ сказано, что они равны дате акта)
    # Но для гибкости можем оставить в модели, инициализируя датой акта
    start_date: date
    end_date: date
    
    # Тип валидатора
    validator_type: str # BM-20, BM-20 QR, BM-20 A
    
    # Серийные номера
    old_validator_sn: str
    new_validator_sn: str
    old_sam_sn: str
    new_sam_sn: str
    
    # SAM активация (опционально)
    old_sam_activation_no: Optional[str] = "-"
    new_sam_activation_no: Optional[str] = "-"
